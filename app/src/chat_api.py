#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
"""

import functools
import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional, Sequence

from asyncer import asyncify
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from literalai import AsyncLiteralClient, Message
from pydantic import BaseModel
from sqlalchemy import select

import chainlit as cl
from chainlit.context import init_http_context
from chainlit.data import get_data_layer
from src import chat_engine
from src.adapters import db
from src.app_config import app_config
from src.chainlit_data import ChainlitPolyDataLayer
from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers
from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Subsection
from src.generate import ChatHistory
from src.healthcheck import HealthCheck, health
from src.util.string_utils import format_highlighted_uri

logger = logging.getLogger(__name__)


@cl.data_layer
def chainlit_data_layer() -> ChainlitPolyDataLayer:
    print("chainlit_data_layer: ChainlitPolyDataLayer()")
    logger.info("chainlit_data_layer: ChainlitPolyDataLayer()")
    return ChainlitPolyDataLayer()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[Any, None]:
    logger.info("Initializing API")
    # Initialize Chainlit Data Layer
    # init_http_context() calls get_data_layer(), which creates an asyncpg connection pool,
    # which is available only in a single event loop used by FastAPI to respond to requests
    init_http_context()
    yield
    logger.info("Cleaning up API")


router = APIRouter(prefix="/api", tags=["Chat API"], lifespan=lifespan)


@router.get("/healthcheck")
async def healthcheck(request: Request) -> HealthCheck:
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


# region: ===================  Session Management ===================


@dataclass
class ChatEngineSettings:
    engine_id: str
    # Non-None settings will be set for the engine
    retrieval_k: Optional[int] = None


@dataclass
class ChatSession:
    user_session: UserSession
    # This user uuid is always retrieved from chainlit data layer so it doesn't need to be stored in the DB
    user_uuid: str | None
    chat_engine_settings: ChatEngineSettings
    allowed_engines: list[str]


def __get_or_create_chat_session(
    user_id: str, session_id: str | None, user_uuid: str | None
) -> ChatSession:
    "Creating/retrieving user's session from the DB"
    if user_session := _load_user_session(session_id):
        logger.info("Found user session %r for: %s", session_id, user_id)
        if user_session.user_id != user_id:
            raise HTTPException(
                status_code=400,
                detail=f"Session {session_id} is not associated with user {user_id}",
            )
    else:
        with dbsession.get().begin():  # session is auto-committed or rolled back upon exception
            logger.info("Creating new user session %r for: %s", session_id, user_id)
            user_session = UserSession(
                session_id=session_id or str(uuid.uuid4()),
                user_id=user_id,
                chat_engine_id="imagine-la",
                lai_thread_id=None,
            )
            dbsession.get().add(user_session)

    return ChatSession(
        user_session=user_session,
        user_uuid=user_uuid,
        chat_engine_settings=ChatEngineSettings(user_session.chat_engine_id),
        allowed_engines=["imagine-la"],
    )


async def _init_chat_session(
    user_id: str,
    session_id: str | None,
    user_meta: Optional[dict] = None,
) -> ChatSession:
    if user_id == "":
        user_id = "EMPTY_USER_ID"  # temporary fix for empty user_id
        # raise HTTPException(status_code=400, detail="user_id must be a non-empty string")

    # Ensure user exists in storage
    # init_http_context() will use stored_user.id as the thread.user_id
    stored_user = await get_data_layer().create_user(
        # display_name isn't persisted in Chainlit data layer
        cl.User(identifier=user_id, display_name=user_id, metadata=user_meta or {})
    )

    # Also associate stored_user.id with the user_id and session
    chat_session = __get_or_create_chat_session(user_id, session_id, user_uuid=stored_user.id)

    # The thread_id is set in store_thread_id() after the thread is automatically created
    thread_id = chat_session.user_session.lai_thread_id
    # Set the thread ID in the http_context so that new cl.Message instances will be associated
    # with the thread when cl.MessageBase.__post_init__() accesses cl.context.session.thread_id.
    # The http_context uses ContextVars to avoid concurrency issues.
    # (There's also an init_ws_context() if we enable websocket support -- see chainlit.socket.py)
    init_http_context(thread_id=thread_id, user=stored_user)

    logger.info("Session %r (user %r): LiteralAI thread_id=%s", session_id, user_id, thread_id)
    return chat_session


def _load_user_session(session_id: str | None) -> Optional[UserSession]:
    if not session_id:
        return None
    with dbsession.get().begin():
        return (
            dbsession.get()
            .scalars(select(UserSession).where(UserSession.session_id == session_id))
            .first()
        )


def _load_chat_history(user_session: UserSession) -> ChatHistory:
    with dbsession.get().begin():
        db_user_session = dbsession.get().merge(user_session)
        session_msgs = db_user_session.chat_messages
        return [{"role": message.role, "content": message.content} for message in session_msgs]


# endregion
# region: ===================  Example API Endpoint and logging to LiteralAI  ===================

dbsession: ContextVar[db.Session] = ContextVar("db_session", default=app_config.db_session())


@asynccontextmanager
async def db_session_context_var() -> AsyncGenerator[db.Session, None]:
    with app_config.db_session() as db_session:
        token = dbsession.set(db_session)
        try:
            # Use dbsession.get() to get the session without having to pass it to nested functions.
            # Use `with dbsession.get().begin():` to auto-committed or rolled back upon exception.
            yield db_session
            # Auto-commit
            db_session.commit()
        finally:
            db_session.close()
            dbsession.reset(token)


# Make sure to use async functions for faster responses
@router.get("/engines")
async def engines(user_id: str, session_id: str | None = None) -> list[str]:
    # async def engines(user_id: Annotated[str, Query(min_length=1)]) -> list[str]:
    async with db_session_context_var():
        user_meta = {"engines": True}
        session = await _init_chat_session(user_id, session_id, user_meta)
        # Only if new session (i.e., lai_thread_id hasn't been set), set the thread name
        thread_name = "API:/engines" if not session.user_session.lai_thread_id else None

        # Use get_data_layer() like in chainlit.server
        data_layer = get_data_layer()

        # A ChatSession is persisted in Thread and user_session tables
        # - A session/thread is associated with only 1 user
        # A Message is persisted in Step and chat_message tables
        # - A message/step can have an author/name
        request_step = cl.Message(
            author=session.user_uuid,  # author become the step.name
            content="List chat engines",  # content becomes the step.output
            type="user_message",
            metadata={
                "user_id": session.user_session.user_id,
            },
        ).to_dict()
        await data_layer.create_step(request_step)

        thread_id = request_step["threadId"]
        assert thread_id
        await store_thread_id(session, thread_id)

        if thread_name:
            await data_layer.update_thread(thread_id=thread_id, name=thread_name)

        response = [
            engine
            for engine in chat_engine.available_engines()
            if engine in session.allowed_engines
        ]

        response_step = cl.Message(
            # author="api_response",
            content=str(response),
            type="system_message",
            parent_id=request_step["id"],
        ).to_dict()
        await data_layer.create_step(response_step)
        return response


class FeedbackRequest(BaseModel):
    user_id: str
    # user_id: Annotated[str, Query(min_length=1)]
    session_id: str
    response_id: str  # id of the chatbot response this feedback is about
    is_positive: bool  # if chatbot response answer is helpful or not
    comment: Optional[str] = None  # user comment for the feedback


@router.post("/feedback")
async def feedback(
    request: FeedbackRequest,
) -> Response:
    """Endpoint for creating feedback for a chatbot response message"""
    await _init_chat_session(request.user_id, request.session_id)
    data_layer = get_data_layer()
    cl_feedback = cl.types.Feedback(
        forId=request.response_id,
        # name=request.user_id,
        value=1 if request.is_positive else 0,
        comment=request.comment,
    )
    await data_layer.upsert_feedback(cl_feedback)
    return Response(status_code=200)


# endregion
# region: ===================  API Endpoints  ===================


class QueryRequest(BaseModel):
    session_id: str
    new_session: bool
    message: str
    user_id: str
    # user_id: Annotated[str, Query(min_length=1)]
    agency_id: Optional[str] = None
    beneficiary_id: Optional[str] = None


class Citation(BaseModel):
    citation_id: str
    source_id: str
    source_name: str
    source_dataset: str
    page_number: Optional[int] | None
    uri: Optional[str] | None
    headings: Sequence[str]
    citation_text: str

    @staticmethod
    def from_subsection(subsection: Subsection) -> "Citation":
        chunk = subsection.chunk
        highlighted_text_src = format_highlighted_uri(chunk.document.source, subsection.text)
        return Citation(
            citation_id=f"citation-{subsection.id}",
            source_id=str(chunk.document.id),
            source_name=chunk.document.name,
            source_dataset=chunk.document.dataset,
            page_number=chunk.page_number,
            uri=highlighted_text_src,
            headings=subsection.text_headings,
            citation_text=subsection.text,
        )


class QueryResponse(BaseModel):
    response_text: str
    alert_message: Optional[str] = None
    citations: list[Citation]

    # Populated after instantiation based on LiteralAI message ID
    response_id: Optional[str] = None


def get_chat_engine(session: ChatSession) -> ChatEngineInterface:
    engine_id = session.chat_engine_settings.engine_id
    # May want to cache engine instances rather than creating them for each request
    engine = chat_engine.create_engine(engine_id) if engine_id in session.allowed_engines else None
    if not engine:
        raise HTTPException(status_code=403, detail=f"Unknown engine: {engine_id}")
    for setting_name in engine.user_settings:
        setting_value = getattr(session.chat_engine_settings, setting_name, None)
        if setting_value is not None:
            setattr(engine, setting_name, setting_value)
    return engine


@router.post("/query")
async def query(request: QueryRequest) -> QueryResponse:
    async with db_session_context_var() as db_session:
        start_time = time.perf_counter()

        user_meta = {"agency_id": request.agency_id, "beneficiary_id": request.beneficiary_id}
        session = await _init_chat_session(request.user_id, request.session_id, user_meta)
        _validate_session(request, session)

        # Load history BEFORE adding the new message to the DB
        chat_history = _load_chat_history(session.user_session)
        _validate_chat_history(request, chat_history)

        data_layer = get_data_layer()

        request_step = cl.Message(
            author=session.user_uuid,
            content=request.message,
            type="user_message",
            metadata={
                "user_id": session.user_session.user_id,
                "request": request.__dict__,
            },
        ).to_dict()
        await data_layer.create_step(request_step)

        thread_id = request_step["threadId"]
        assert thread_id
        await store_thread_id(session, thread_id)

        # Only if new session, set the LiteralAI thread name; don't want the thread name to change otherwise
        if request.new_session:
            thread_name = request.message.strip().splitlines()[0] or "API:/query"
            await data_layer.update_thread(thread_id=thread_id, name=thread_name)

        engine = get_chat_engine(session)
        response, metadata = await run_query(engine, request.message, chat_history)

        # Example of using parent_id to have a hierarchy of messages in Literal AI
        response_step = cl.Message(
            content=response.response_text,
            type="assistant_message",
            parent_id=request_step["id"],
            metadata={
                "citations": [c.__dict__ for c in response.citations],
                "chat_history": chat_history,
            }
            | metadata,
        ).to_dict()
        await data_layer.create_step(response_step)
        # An id is needed to later provide feedback on this message
        response.response_id = response_step["id"]

        duration = time.perf_counter() - start_time
        logger.info(f"Total /query endpoint execution took {duration:.2f} seconds")

        # If successful, update the DB; otherwise the DB will contain questions without responses
        with db_session.begin():
            # Now, add request and response messages to DB to be used for chat history in subsequent requests
            # TODO: Update _load_chat_history() to use Step records and remove ChatMessage table
            db_session.add(
                ChatMessage(session_id=request.session_id, role="user", content=request.message)
            )
            db_session.add(
                ChatMessage(
                    session_id=request.session_id,
                    role="assistant",
                    content=response.response_text,
                )
            )
    return response


async def store_thread_id(session: ChatSession, thread_id: str) -> None:
    # Update the DB with the LiteralAI thread ID, regardless of other DB updates,
    # so do this is its own DB transaction.
    # lai_thread_id is None when request.new_session=True
    # A thread_id is not created until the first message logged in LiteralAi
    if not session.user_session.lai_thread_id and thread_id:
        with dbsession.get().begin():
            session.user_session.lai_thread_id = thread_id
            logger.info(
                "Started new session with thread_id: %s",
                session.user_session.lai_thread_id,
            )
            dbsession.get().merge(session.user_session)

        # lai_dl = get_data_layer().data_layers[1]
        # assert isinstance(lai_dl.client, AsyncLiteralClient)
        # Workaround/fix: When using the chainlit_data_layer, the participant_id is not set.
        """
        When calling client.api.update_thread(id=thread_id, participant_id=session.user_session.user_id),
        we get "Thread violates foreign key constraint Thread_participantId_fkey" b/c need to pass in
        the UUID from the Postgres database.
        In LiteralAI thread export, identifier comes from the Postgres database user.id:
            "participant": {
            "id": "b939dbdc-7cfe-4b74-b7a8-7fb1c87e5793",
            "identifier": "9dec2129-b70c-4a49-9cff-d1f8d366b951"
            },

        This works but it creates a new user in LiteralAI with the user.identifier = Postgres user.id
        with no associated threads.
        """
        # lai_user = await lai_dl.client.api.get_user(session.user_session.user_id)
        # await lai_dl.client.api.update_thread(id=thread_id, participant_id=session.user_uuid)
        # assert lai_user.id == session.user_uuid


def _validate_session(request: QueryRequest, session: ChatSession) -> None:
    # Check if request is consistent with LiteralAI thread
    if request.new_session and session.user_session.lai_thread_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot start a new session {request.session_id!r} that is "
                f"already associated with thread_id {session.user_session.lai_thread_id!r}"
            ),
        )

    if not request.new_session and not session.user_session.lai_thread_id:
        raise HTTPException(
            status_code=409,
            detail=f"LiteralAI thread ID for existing session {request.session_id!r} not found",
        )


def _validate_chat_history(request: QueryRequest, chat_history: ChatHistory) -> None:
    if request.new_session and chat_history:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start a new session with an existing session_id: {request.session_id}",
        )
    if not request.new_session and not chat_history:
        raise HTTPException(
            status_code=409,
            detail=f"Chat history for existing session not found: {request.session_id}",
        )


# Temporarily True until API client handles alert_message field
INCLUDE_ALERT_IN_RESPONSE = True


async def run_query(
    engine: ChatEngineInterface, question: str, chat_history: Optional[ChatHistory] = None
) -> tuple[QueryResponse, dict[str, Any]]:
    logger.info("Received: '%s' with history: %s", question, chat_history)
    result = await asyncify(lambda: engine.on_message(question, chat_history))()
    logger.info("Response: %s", result.response)

    final_result = simplify_citation_numbers(result)
    citations = [Citation.from_subsection(subsection) for subsection in final_result.subsections]

    alert_msg = getattr(result.attributes, "alert_message", None)

    if INCLUDE_ALERT_IN_RESPONSE and alert_msg:
        response_msg = f"{alert_msg}\n\n{final_result.response}"
    else:
        response_msg = final_result.response
    return (
        QueryResponse(
            response_text=response_msg,
            alert_message=alert_msg,
            citations=citations,
        ),
        {"attributes": result.attributes.model_dump()},
    )


# endregion

logger.info("Chat API loaded with routes: %s", router.routes)

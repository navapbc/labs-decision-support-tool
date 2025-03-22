#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
"""

import functools
import logging
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Generator, Optional, Sequence

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
    # init_http_context() calls get_data_layer(), which creates a asyncpg connection pool,
    # which is available only in a single event loop used by FastAPI to respond to requests.
    init_http_context()
    yield
    logger.info("Cleaning up API")
    # Clean up


router = APIRouter(prefix="/api", tags=["Chat API"], lifespan=lifespan)


@router.get("/healthcheck")
async def healthcheck(request: Request) -> HealthCheck:
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


@functools.cache
def literalai() -> AsyncLiteralClient:
    """
    This needs to be a function so that it's not immediately instantiated upon
    import of this module and so that it can mocked in tests.
    """
    if app_config.literal_api_key_for_api:
        return AsyncLiteralClient(api_key=app_config.literal_api_key_for_api)
    return AsyncLiteralClient()


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


async def _get_chat_session(
    user_id: str,
    session_id: str | None,
    user_meta: Optional[dict] = None,
) -> ChatSession:
    if user_id == "":
        user_id = "EMPTY_USER_ID"  # temporary fix for empty user_id
        # raise HTTPException(status_code=400, detail="user_id must be a non-empty string")

    # Ensure user exists in Literal AI
    literalai_user = await literalai().api.get_or_create_user(user_id, user_meta)
    # Ensure user exists in storage
    # init_http_context() will use stored_user.id as the thread.user_id
    user_meta = user_meta or {}
    user_meta |= {"uuid": literalai_user.id}
    stored_user = await get_data_layer().create_user(
        cl.User(identifier=user_id, display_name=user_id, metadata=user_meta)
    )
    # display_name isn't persisted in Chainlit data layer

    # Set the LiteralAI user ID for this session so it can be used in literalai().thread()
    chat_session = __get_or_create_chat_session(user_id, session_id, user_uuid=stored_user.id)
    thread_id = chat_session.user_session.lai_thread_id

    # Set the thread ID in the http_context so new cl.Message instances will be associated with the thread
    # when cl.MessageBase.__post_init__() accesses cl.context.session.thread_id.
    # The http_context uses ContextVars to avoid concurrency issues.
    # (There's also an init_ws_context() if we enable websocket support
    # see chainlit.socket.py for how it's used)
    init_http_context(thread_id=thread_id, user=stored_user)

    logger.info(
        "Session %r (user %r): LiteralAI thread_id=%s",
        session_id,
        user_id,
        chat_session.user_session.lai_thread_id,
    )
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


@contextmanager
def db_session_context_var() -> Generator[db.Session, None, None]:
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
    with db_session_context_var():
        user_meta = {"engines": True}
        session = await _get_chat_session(user_id, session_id, user_meta)
        thread_name = "API:/engines" if not session.user_session.lai_thread_id else None

        # Use get_data_layer() like in chainlit.server
        data_layer = get_data_layer()

        # A ChatSession is persisted in Thread and user_session tables
        # - A session/thread is associated with only 1 user
        # A Message is persisted in Step and chat_message tables
        # - A message/step can have an author/name
        request_step = cl.Message(
            # with literalai().thread(name=thread_name, participant_id=session.literalai_user_id):
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
            metadata={
                "user_id": session.user_session.user_id,
            },
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
    # API endpoint to send feedback https://docs.literalai.com/guides/logs#add-a-score
    response = await literalai().api.create_score(
        step_id=request.response_id,
        name=request.user_id,
        type="HUMAN",
        value=1 if request.is_positive else 0,
        comment=request.comment,
    )
    logger.info("Received feedback value: %s for response_id %s", response.value, response.step_id)
    if response.comment:
        logger.info("Received comment: %s", response.comment)

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
    with db_session_context_var() as db_session:
        start_time = time.perf_counter()

        user_meta = {"agency_id": request.agency_id, "beneficiary_id": request.beneficiary_id}
        session = await _get_chat_session(request.user_id, request.session_id, user_meta)
        _validate_session_against_literalai(request, session)

        # Load history BEFORE adding the new message to the DB
        chat_history = _load_chat_history(session.user_session)
        _validate_chat_history(request, chat_history)

        thread_name = None
        # Only if new session, set the LiteralAI thread name; don't want the thread name to change otherwise
        if request.new_session:
            thread_name = request.message.strip().splitlines()[0] or "API:/query"

        with literalai().thread(
            name=thread_name,
            participant_id=session.user_uuid,
            thread_id=session.user_session.lai_thread_id,
        ):
            # Log the message to LiteralAI
            request_msg = literalai().message(
                content=request.message,
                type="user_message",
                name=request.session_id,
                metadata={
                    "request": request.__dict__,
                    "user_id": session.user_session.user_id,
                },
            )
            _validate_literalai_message(session, request_msg)

            await store_thread_id(session, request_msg.thread_id)

            engine = get_chat_engine(session)
            response, metadata = await run_query(engine, request.message, chat_history)

            # Example of using parent_id to have a hierarchy of messages in Literal AI
            response_msg = literalai().message(
                content=response.response_text,
                type="assistant_message",
                parent_id=request_msg.id,
                metadata={
                    "citations": [c.__dict__ for c in response.citations],
                    "chat_history": chat_history,
                }
                | metadata,
            )
            # id needed to later provide feedback on this message in LiteralAI
            response.response_id = response_msg.id

        duration = time.perf_counter() - start_time
        logger.info(f"Total /query endpoint execution took {duration:.2f} seconds")

        # If successful, update the DB; otherwise the DB will contain questions without responses
        with db_session.begin():
            # Now, add request and response messages to DB
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


async def store_thread_id(session: ChatSession, thread_id: str | None) -> None:
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

        lai_dl = get_data_layer().data_layers[1]
        assert isinstance(lai_dl.client, AsyncLiteralClient)
        # Workaround/fix: When using the chainlit_data_layer, the participant_id is not set. LiteralAI shows
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


def _validate_session_against_literalai(request: QueryRequest, session: ChatSession) -> None:
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


def _validate_literalai_message(session: ChatSession, lai_req_msg: Message) -> None:
    if not lai_req_msg.thread_id:
        # Should never happen
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected: thread_id is not set on LiteralAI message: {lai_req_msg}",
        )

    if (
        session.user_session.lai_thread_id
        and session.user_session.lai_thread_id != lai_req_msg.thread_id
    ):
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected: LiteralAI thread ID mismatch: {session.user_session.lai_thread_id} != {lai_req_msg.thread_id}",
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

#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Coroutine, Generator, Optional, Sequence, Union

from asyncer import asyncify
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from lazify import LazyProxy
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

import chainlit as cl
from chainlit.context import init_http_context as cl_init_context
from chainlit.data import get_data_layer as cl_get_data_layer
from chainlit.step import StepDict
from src import chat_engine
from src.adapters import db
from src.app_config import app_config
from src.chainlit_data import ChainlitPolyDataLayer, get_literal_data_layer, get_postgres_data_layer
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
    data_layers = None
    if app_config.literal_api_key_for_api:
        data_layers = [
            get_postgres_data_layer(os.environ.get("DATABASE_URL")),
            get_literal_data_layer(app_config.literal_api_key_for_api),
        ]
    logger.info("API: creating chainlit_data_layer: ChainlitPolyDataLayer(%r)", data_layers)
    return ChainlitPolyDataLayer(data_layers)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[Any, None]:
    logger.info("Initializing API")
    # Initialize Chainlit Data Layer
    # cl_init_context() calls get_data_layer(), which creates an asyncpg connection pool,
    # which is available only in a single event loop used by FastAPI to respond to requests
    cl_init_context()
    yield
    logger.info("Cleaning up API")


router = APIRouter(prefix="/api", tags=["Chat API"], lifespan=lifespan)


@router.get("/healthcheck")
async def healthcheck(request: Request) -> HealthCheck:
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


@router.get("/streaming-test", response_class=HTMLResponse)
async def streaming_test() -> str:
    """Serve the streaming test HTML page"""
    html_path = Path(__file__).parent.parent / "streaming-test.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Streaming test page not found")
    
    return html_path.read_text()


# region: ===================  Session Management ===================


@dataclass
class ChatEngineSettings:
    engine_id: str
    # Non-None settings will be set for the engine
    retrieval_k: Optional[int] = None


@dataclass
class ChatSession:
    user_session: UserSession
    is_new: bool
    chat_engine_settings: ChatEngineSettings
    allowed_engines: list[str]
    # This user uuid is always retrieved from chainlit data layer so it doesn't need to be stored in the DB
    user_uuid: str | None = None


def __get_or_create_chat_session(
    user_id: str, session_id: str | None, new_session: bool
) -> ChatSession:
    "Creating/retrieving user's session from the DB"
    if user_session := _load_user_session(session_id):
        if new_session:
            raise HTTPException(
                status_code=409,
                detail=(f"Cannot start a new session {session_id!r} that already exists"),
            )

        logger.info("Found user session %r for: %s", session_id, user_id)
        if user_session.user_id != user_id:
            raise HTTPException(
                status_code=409,
                detail=f"Session {session_id!r} is not associated with user {user_id!r}",
            )
        session_created = False
    elif new_session:
        with dbsession.get().begin():  # session is auto-committed or rolled back upon exception
            user_session = UserSession(
                session_id=session_id or str(uuid.uuid4()),
                user_id=user_id,
                chat_engine_id="imagine-la",
                # Assign a new thread ID for the session
                # This will be used as Message/Step.thread_id and Thread.id when they're created
                lai_thread_id=str(uuid.uuid4()),
            )
            logger.info(
                "Creating new user session %r (thread.id %r) for user %r",
                user_session.session_id,
                user_session.lai_thread_id,
                user_id,
            )
            dbsession.get().add(user_session)
        session_created = True
    else:
        raise HTTPException(
            status_code=409,
            detail=f"Existing session {session_id!r} not found",
        )

    return ChatSession(
        user_session=user_session,
        is_new=session_created,
        chat_engine_settings=ChatEngineSettings(user_session.chat_engine_id),
        allowed_engines=["imagine-la"],
    )


async def __ensure_user_exists(
    user_id: str, user_meta: Optional[dict], new_session: bool
) -> cl.PersistedUser:
    stored_user = await cl_get_data_layer().get_user(user_id)
    if not stored_user and not new_session:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found")

    if stored_user and user_meta:
        # Merge metadata from the stored user with user_meta if key doesn't already exist
        for key, value in stored_user.metadata.items():
            if key not in user_meta:
                user_meta[key] = value
        # If metadata is the same, assume there's no metadata to update
        if user_meta == stored_user.metadata:
            user_meta = None

    # If user doesn't exist or there is new metadata, create or update the user
    if not stored_user or user_meta:
        stored_user = await cl_get_data_layer().create_user(
            # display_name isn't persisted in Chainlit data layer
            cl.User(identifier=user_id, display_name=user_id, metadata=user_meta or {})
        )

    return stored_user


async def _init_chat_session(
    user_id: str,
    session_id: str | None,
    user_meta: Optional[dict] = None,
    new_session: bool = True,
) -> ChatSession:
    if user_id == "":
        user_id = "EMPTY_USER_ID"  # temporary fix for empty user_id
        # raise HTTPException(status_code=400, detail="user_id must be a non-empty string")

    # Also associate stored_user.id with the user_id and session
    chat_session = __get_or_create_chat_session(user_id, session_id, new_session)

    # Ensure user exists in storage
    stored_user = await __ensure_user_exists(user_id, user_meta, new_session)

    # cl_init_context() will use stored_user.id as the thread.user_id
    chat_session.user_uuid = stored_user.id

    # The thread_id is set in store_thread_id() after the thread is automatically created
    thread_id = chat_session.user_session.lai_thread_id
    # Set the thread ID in the http_context so that new cl.Message instances will be associated
    # with the thread when cl.MessageBase.__post_init__() accesses cl.context.session.thread_id.
    # The http_context uses ContextVars to avoid concurrency issues.
    # (There's also an init_ws_context() if we enable websocket support -- see chainlit.socket.py)
    cl_init_context(thread_id=thread_id, user=stored_user)
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

dbsession: ContextVar[db.Session] = ContextVar(
    "api_db_session", default=LazyProxy(app_config.db_session(), enable_cache=False)
)


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


async def persist_messages(
    request_step: StepDict,
    thread_name: str | None,
    process_request: Coroutine[None, None, tuple[Any, StepDict]],
) -> tuple[Any, StepDict]:
    """Asynchronously persist request and response messages

    A ChatSession is persisted in Thread and user_session tables
    - A session/thread is associated with only 1 user
    A Message is persisted in Step and chat_message tables
    - A message/step can have an author/name
    """
    tasks = []
    # Use get_data_layer() like in chainlit.server
    data_layer = cl_get_data_layer()
    # Creating the first step in a thread will also create the associated thread
    tasks.append(asyncio.create_task(data_layer.create_step(request_step)))

    if thread_name:
        # In the data layer, update_thread() can execute before or after create_step()
        tasks.append(
            asyncio.create_task(
                data_layer.update_thread(thread_id=request_step["threadId"], name=thread_name)
            )
        )

    # Wait for all tasks to finish before persisting response_step
    results = await asyncio.gather(process_request, *tasks)
    # Get result from process_request
    response, response_step = results[0]
    await data_layer.create_step(response_step)
    return response, response_step


# Make sure to use async functions for faster responses
@router.get("/engines")
async def engines(user_id: str, session_id: str | None = None) -> list[str]:
    # async def engines(user_id: Annotated[str, Query(min_length=1)]) -> list[str]:
    with db_session_context_var():
        user_meta = {"engines": True}
        session = await _init_chat_session(user_id, session_id, user_meta)
        # Only if new session (i.e., lai_thread_id hasn't been set), set the thread name
        thread_name = "API:/engines" if session.is_new else None

        request_step = cl.Message(
            content="List chat engines",  # content becomes the step.output
            author=session.user_session.user_id,  # author becomes the step.name
            type="user_message",
            metadata={
                "user_id": session.user_session.user_id,
                "user_uuid": session.user_uuid,
            },
        ).to_dict()

        async def process_request() -> tuple[list[str], StepDict]:
            response = [
                engine
                for engine in chat_engine.available_engines()
                if engine in session.allowed_engines
            ]

            resp_msg = cl.Message(
                content=str(response),
                type="system_message",
                # Set parent_id to have a hierarchy of messages in the thread
                parent_id=request_step["id"],
            ).to_dict()

            return response, resp_msg

        response, _resp_step = await persist_messages(request_step, thread_name, process_request())
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
    with db_session_context_var():
        try:
            await _init_chat_session(request.user_id, request.session_id, new_session=False)
            await cl_get_data_layer().upsert_feedback(
                cl.types.Feedback(
                    forId=request.response_id,
                    value=1 if request.is_positive else 0,
                    comment=request.comment,
                )
            )
            return Response(status_code=200)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error: {e}",
            ) from e


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


class QueryInitRequest(BaseModel):
    session_id: str
    new_session: bool
    question: str
    user_id: str
    agency_id: Optional[str] = None
    beneficiary_id: Optional[str] = None


class QueryInitResponse(BaseModel):
    status: str = "processing"
    message_id: str


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

        user_meta = {}
        if request.agency_id is not None:
            user_meta["agency_id"] = request.agency_id
        if request.beneficiary_id is not None:
            user_meta["beneficiary_id"] = request.beneficiary_id

        session = await _init_chat_session(
            request.user_id, request.session_id, user_meta, request.new_session
        )

        # Load history BEFORE adding the new message to the DB
        chat_history = _load_chat_history(session.user_session)
        _validate_chat_history(request, chat_history)

        # Only if new session, set the LiteralAI thread name; don't want the thread name to change otherwise
        thread_name = request.message.strip().splitlines()[0] if request.new_session else None
        request_step = cl.Message(
            author=session.user_session.user_id,
            content=request.message,
            type="user_message",
            metadata={
                "user_id": session.user_session.user_id,
                "user_uuid": session.user_uuid,
                "request": request.__dict__,
            },
        ).to_dict()

        async def process_request() -> tuple[QueryResponse, StepDict]:
            engine = get_chat_engine(session)
            response, metadata = await run_query(engine, request.message, chat_history)

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
            return response, response_step

        response, response_step = await persist_messages(
            request_step, thread_name, process_request()
        )
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


# New endpoints for Streaming API

@router.post("/query_init")
async def query_init(request: QueryInitRequest) -> QueryInitResponse:
    """
    Initializes a streaming query by storing the question and creating a message_id.
    Returns the message_id that the client will use to fetch the streaming response.
    """
    with db_session_context_var() as db_session:
        user_meta = {}
        if request.agency_id is not None:
            user_meta["agency_id"] = request.agency_id
        if request.beneficiary_id is not None:
            user_meta["beneficiary_id"] = request.beneficiary_id

        session = await _init_chat_session(
            request.user_id, request.session_id, user_meta, request.new_session
        )

        # Load history to validate
        chat_history = _load_chat_history(session.user_session)
        _validate_chat_history(request, chat_history)

        # Create chainlit message for the question
        thread_name = request.question.strip().splitlines()[0] if request.new_session else None
        request_step = cl.Message(
            author=session.user_session.user_id,
            content=request.question,
            type="user_message",
            metadata={
                "user_id": session.user_session.user_id,
                "user_uuid": session.user_uuid,
                "request": {
                    "message": request.question,
                    "user_id": request.user_id,
                    "agency_id": request.agency_id,
                    "session_id": request.session_id,
                    "new_session": request.new_session,
                    "beneficiary_id": request.beneficiary_id
                },
                "language": None,
                "showInput": None,
                "waitForAnswer": False
            },
        ).to_dict()

        # Persist the question message
        data_layer = cl_get_data_layer()
        await data_layer.create_step(request_step)
        if thread_name:
            await data_layer.update_thread(thread_id=request_step["threadId"], name=thread_name)

        # Store the question in the database
        with db_session.begin():
            db_session.add(
                ChatMessage(session_id=request.session_id, role="user", content=request.question)
            )

        # The message_id is used to refer to this specific question/answer pair
        message_id = request_step["id"]

        return QueryInitResponse(status="processing", message_id=message_id)


@router.get("/query_stream")
async def query_stream(request: Request, id: str, user_id: str, session_id: str):
    """
    Streams the response for a query initiated with query_init.
    Uses Server-Sent Events (SSE) to stream the response chunks to the client.
    """
    with db_session_context_var() as db_session:
        # Get session information
        session = await _init_chat_session(user_id, session_id, new_session=False)
        chat_history = _load_chat_history(session.user_session)
        engine = get_chat_engine(session)

        # Retrieve the question from the database
        with db_session.begin():
            question = db_session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            ).first()

            if not question or question.role != "user":
                raise HTTPException(status_code=404, detail="Question not found")

        # Prepare response placeholder for storing the full response
        full_response = ""
        
        # We need to retrieve the subsections for citations, but without making a separate LLM call
        subsections = []
        retrieval_done = False
        
        # Create an SSE generator that streams chunks
        async def event_generator():
            nonlocal full_response, subsections, retrieval_done
            
            try:
                # Get the alert_message by analyzing the user message
                # This needs to be done before generating the response
                attributes = await asyncify(
                    lambda: engine.analyze_message(question.content)
                )()
                
                alert_message = getattr(attributes, "alert_message", None)
                
                # If there's an alert message, send it first
                if INCLUDE_ALERT_IN_RESPONSE and alert_message:
                    yield {
                        "event": "alert",
                        "data": alert_message
                    }
                
                # If we need context, retrieve it ourselves to avoid duplicate retrieval
                if getattr(attributes, "needs_context", True):
                    # This mirrors the logic in on_message_streaming but captures the subsections
                    question_for_retrieval = getattr(attributes, "translated_message", "") or question.content
                    
                    # Retrieve context (same as in chat_engine.py)
                    chunks_with_scores = await asyncify(lambda: engine.retrieve_context(question_for_retrieval))()
                    chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
                    subsections = await asyncify(lambda: engine.prepare_subsections(chunks))()
                    retrieval_done = True
                
                # Stream the response using the engine's streaming method
                async for chunk in engine.on_message_streaming(question.content, chat_history):
                    if await request.is_disconnected():
                        # Client disconnected, stop streaming
                        break
                    
                    full_response += chunk
                    
                    # Send the chunk
                    yield {
                        "event": "chunk",
                        "data": chunk
                    }
                
                # After streaming is complete, we need to process citations
                # Process the citations from the subsections - use our cached subsections if available
                from src.citations import simplify_citation_numbers
                
                # If we didn't retrieve context earlier, we need to do it now
                if not retrieval_done:
                    # Use a lightweight method to get subsections
                    question_for_retrieval = getattr(attributes, "translated_message", "") or question.content
                    chunks_with_scores = await asyncify(lambda: engine.retrieve_context(question_for_retrieval))()
                    chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
                    subsections = await asyncify(lambda: engine.prepare_subsections(chunks))()
                
                # Process citations with the cached response and subsections
                final_result = simplify_citation_numbers(full_response.strip(), subsections)
                
                # Extract citations from the result
                citations = [Citation.from_subsection(subsection) for subsection in final_result.subsections]
                
                # Create response step in the same format as the regular query endpoint
                response_step = cl.Message(
                    content=full_response.strip(),
                    type="assistant_message",
                    parent_id=id,  # This is the request_step id passed in from query_init
                    metadata={
                        "citations": [c.model_dump() for c in citations],
                        "chat_history": chat_history,
                        "attributes": attributes.model_dump(),
                        "language": None,
                        "showInput": None,
                        "waitForAnswer": False
                    }
                ).to_dict()
                
                # Persist the step
                await cl_get_data_layer().create_step(response_step)
                
                # Send a done event with citations - convert to JSON string for SSE compatibility
                import json
                citations_json = json.dumps([c.model_dump() for c in citations])
                yield {
                    "event": "done",
                    "data": citations_json
                }
                
                # Save the complete response to the database
                with db_session.begin():
                    db_session.add(
                        ChatMessage(
                            session_id=session_id,
                            role="assistant",
                            content=full_response.strip()
                        )
                    )
                
            except Exception as e:
                logger.exception("Error during streaming: %s", e)
                yield {
                    "event": "error",
                    "data": str(e)
                }
                
        return EventSourceResponse(event_generator())
                

def _validate_chat_history(request: Union[QueryRequest, QueryInitRequest], chat_history: ChatHistory) -> None:
    if request.new_session and chat_history:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start a new session with an existing chat_history: {request.session_id}",
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
    final_result = simplify_citation_numbers(result.response, result.subsections)
    logger.info("Response: %s", final_result.response)
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

#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
"""

import functools
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Request, Response
from literalai import AsyncLiteralClient
from pydantic import BaseModel
from sqlalchemy import select

from src import chat_engine
from src.adapters import db
from src.app_config import app_config
from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers
from src.db.models.conversation import ChatMessage
from src.db.models.document import Subsection
from src.generate import ChatHistory
from src.healthcheck import HealthCheck, health

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Chat API"])


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
    return AsyncLiteralClient()


# region: ===================  Session Management ===================


@dataclass
class UserInfo:
    user_id: str
    allowed_engines: list[str]


@dataclass
class ChatEngineSettings:
    engine_id: str
    retrieval_k: Optional[int] = None


@dataclass
class UserSession:
    user: UserInfo
    chat_engine_settings: ChatEngineSettings
    literalai_user_id: Optional[str] = None
    message_history: Optional[Sequence[ChatMessage]] = None


def __query_user_session(user_id: str) -> UserSession:
    """
    Placeholder for creating/retrieving user's session from the DB, including settings and constraints
    """
    session = UserSession(
        user=UserInfo(user_id, ["imagine-la"]),
        chat_engine_settings=ChatEngineSettings("imagine-la"),
    )
    logger.info("Found user session for: %s", user_id)
    return session


async def _get_user_session(user_id: str) -> UserSession:
    session = __query_user_session(user_id)
    # Ensure user exists in Literal AI
    literalai_user = await literalai().api.get_or_create_user(user_id, session.user.__dict__)
    # Set the LiteralAI user ID for this session so it can be used in literalai().thread()
    session.literalai_user_id = literalai_user.id
    return session


def _load_chat_history(db_session: db.Session, session_id: str) -> ChatHistory:
    session_msgs = db_session.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return [{"role": message.role, "content": message.content} for message in session_msgs]


# endregion
# region: ===================  Example API Endpoint and logging to LiteralAI  ===================


# Make sure to use async functions for faster responses
@router.get("/engines")
async def engines(user_id: str) -> list[str]:
    session = await _get_user_session(user_id)
    # Example of using Literal AI to log the request and response
    with literalai().thread(name="API:/engines", participant_id=session.literalai_user_id):
        request_msg = literalai().message(
            content="List chat engines",
            type="user_message",
            name=user_id,
            metadata=session.user.__dict__,
        )
        # This will show up as a separate step in LiteralAI, showing input and output
        with literalai().step(type="tool"):
            response = [
                engine
                for engine in chat_engine.available_engines()
                if engine in session.user.allowed_engines
            ]
        # Example of using parent_id to have a hierarchy of messages in Literal AI
        literalai().message(content=str(response), type="system_message", parent_id=request_msg.id)

    return response


class FeedbackRequest(BaseModel):
    session_id: str
    is_positive: bool
    response_id: str
    comment: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/feedback")
async def feedback(
    request: FeedbackRequest,
) -> Response:
    """Endpoint for creating feedback for a chatbot response message

    Args:
        request (FeedbackRequest):
        session_id: the session id, used if user_id is None
        is_positive: if chatbot response answer is helpful or not
        response_id: the response_id of the chatbot response
        comment: user comment for the feedback
        user_id: the user's id

    Returns:
        FeedbackResponse
        user_id: the user's id
        value: 1 if is_positive was "true" and 0 if is_positive was "false"
        step_id: ID of the step associated with the score
        comment: the initial user comment for the feedback
    """
    user_session_id = request.user_id if request.user_id else request.session_id

    session = await _get_user_session(user_session_id)
    # API endpoint to send feedback https://docs.literalai.com/guides/logs#add-a-score
    response = await literalai().api.create_score(
        step_id=request.response_id,
        name=session.user.user_id,
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

    user_id: Optional[str] = None
    agency_id: Optional[str] = None
    beneficiary_id: Optional[str] = None


class Citation(BaseModel):
    citation_id: str
    source_id: str
    source_name: str
    page_number: Optional[int] | None
    uri: Optional[str] | None
    headings: Sequence[str]
    citation_text: str

    @staticmethod
    def from_subsection(subsection: Subsection) -> "Citation":
        chunk = subsection.chunk
        return Citation(
            citation_id=f"citation-{subsection.id}",
            source_id=str(chunk.document.id),
            source_name=chunk.document.name,
            page_number=chunk.page_number,
            uri=chunk.document.source,
            headings=subsection.text_headings,
            citation_text=subsection.text,
        )


class QueryResponse(BaseModel):
    response_text: str
    citations: list[Citation]

    # Populated after instantiation based on LiteralAI message ID
    response_id: Optional[str] = None


def get_chat_engine(session: UserSession) -> ChatEngineInterface:
    engine_id = session.chat_engine_settings.engine_id
    # May want to cache engine instances rather than creating them for each request
    engine = (
        chat_engine.create_engine(engine_id) if engine_id in session.user.allowed_engines else None
    )
    if not engine:
        raise HTTPException(status_code=403, detail=f"Unknown engine: {engine_id}")
    for setting_name in engine.user_settings:
        if setting_value := getattr(session.chat_engine_settings, setting_name, None):
            setattr(engine, setting_name, setting_value)
    return engine


@router.post("/query")
async def query(request: QueryRequest) -> QueryResponse:
    user_session_id = request.user_id if request.user_id else request.session_id
    session = await _get_user_session(user_session_id)
    with (
        literalai().thread(name="API:/query", participant_id=session.literalai_user_id),
        app_config.db_session() as db_session,
        db_session.begin(),  # session is auto-committed or rolled back upon exception
    ):
        request_msg = literalai().message(
            content=request.message,
            type="user_message",
            name=request.session_id,
            metadata={
                "request": request.__dict__,
                "user": session.user.__dict__,
            },
        )
        # Load history BEFORE saving the new message
        chat_history = _load_chat_history(db_session, request.session_id)
        if request.new_session and chat_history:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot start a new session with existing session_id: {request.session_id}",
            )
        elif not request.new_session and not chat_history:
            raise HTTPException(
                status_code=409,
                detail=f"Chat history for existing session not found: {request.session_id}",
            )

        db_session.add(
            ChatMessage(session_id=request.session_id, role="user", content=request.message)
        )

        engine = get_chat_engine(session)
        response: QueryResponse = await run_query(engine, request.message, chat_history)

        # Example of using parent_id to have a hierarchy of messages in Literal AI
        response_msg = literalai().message(
            content=response.response_text,
            type="assistant_message",
            parent_id=request_msg.id,
            metadata={"citations": [c.__dict__ for c in response.citations]},
        )
        # id needed to later provide feedback on this message in LiteralAI
        response.response_id = response_msg.id

        db_session.add(
            ChatMessage(
                session_id=request.session_id,
                role="assistant",
                content=response.response_text,
            )
        )
    return response


async def run_query(
    engine: ChatEngineInterface, question: str, chat_history: Optional[ChatHistory] = None
) -> QueryResponse:
    logger.info("Received: %s with history: %s", question, chat_history)
    result = await asyncify(lambda: engine.on_message(question, chat_history))()
    logger.info("Response: %s", result.response)

    final_result = simplify_citation_numbers(result)
    citations = [Citation.from_subsection(subsection) for subsection in final_result.subsections]
    return QueryResponse(response_text=final_result.response, citations=citations)


# endregion

logger.info("Chat API loaded with routes: %s", router.routes)

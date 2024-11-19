#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
This is enabled with the Chainlit chatbot or can be launched as a standalone app.
"""

import functools
import logging
from dataclasses import dataclass
from typing import Optional

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Request
from literalai import AsyncLiteralClient
from pydantic import BaseModel

from src import chat_engine
from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers
from src.db.models.document import Subsection
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
    This needs to be a function so that it's not immediated instantiated upon
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


def __query_user_session(user_id: str) -> UserSession:
    """
    Placeholder for creating/retrieving user's session from the DB, including settings and constraints
    """
    session = UserSession(
        user=UserInfo(user_id, ["ca-edd-web"]),
        chat_engine_settings=ChatEngineSettings("ca-edd-web"),
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
    headings: Optional[list[str]] | None
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
            headings=chunk.headings,
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
        raise HTTPException(status_code=406, detail=f"Unknown engine: {engine_id}")
    for setting_name in engine.user_settings:
        if setting_value := getattr(session.chat_engine_settings, setting_name, None):
            setattr(engine, setting_name, setting_value)
    return engine


@router.post("/query")
async def query(request: QueryRequest) -> QueryResponse:
    # For now, use the required session_id as the user_id to get a UserSession
    session = await _get_user_session(request.session_id)
    with literalai().thread(name="API:/query", participant_id=session.literalai_user_id):
        request_msg = literalai().message(
            content=request.message,
            type="user_message",
            name=request.session_id,
            metadata={
                "request": request.__dict__,
                "user": session.user.__dict__,
            },
        )

        # May want to cache engine instances rather than creating them for each request
        engine = get_chat_engine(session)
        response: QueryResponse = await run_query(engine, request.message)

        # Example of using parent_id to have a hierarchy of messages in Literal AI
        response_msg = literalai().message(
            content=response.response_text,
            type="assistant_message",
            parent_id=request_msg.id,
            metadata={"citations": [c.__dict__ for c in response.citations]},
        )
        # id needed to later provide feedback on this message in LiteralAI
        response.response_id = response_msg.id
    return response


async def run_query(engine: ChatEngineInterface, question: str) -> QueryResponse:
    logger.info("Received: %s", question)
    chat_history = None
    result = await asyncify(lambda: engine.on_message(question, chat_history))()
    logger.info("Response: %s", result.response)

    final_result = simplify_citation_numbers(result)
    citations = [Citation.from_subsection(subsection) for subsection in final_result.subsections]
    return QueryResponse(response_text=final_result.response, citations=citations)


# endregion

logger.info("Chat API loaded with routes: %s", router.routes)


def main() -> None:  # pragma: no cover
    import getopt
    import sys

    import uvicorn
    from fastapi import FastAPI

    # Use default port 8001 so that this standalone API app does not conflict with the Chainlit app
    port = 8001

    options, _ = getopt.getopt(sys.argv[1:], "p:")
    for opt, arg in options:
        if opt in ("-p"):
            port = int(arg)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # nosec

#!/usr/bin/env python3

"""
This creates API endpoints using FastAPI, which is compatible with Chainlit.
This is enabled with the Chainlit chatbot or can be launched as a standalone app.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from literalai import AsyncLiteralClient
from pydantic import BaseModel

from src import chat_engine
from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers
from src.db.models.document import Subsection
from src.healthcheck import HealthCheck, health

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/healthcheck", response_class=JSONResponse)
async def healthcheck(request: Request) -> HealthCheck:
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


literalai = AsyncLiteralClient()

# region: ===================  Session Management ===================


@dataclass
class UserInfo:
    username: str
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


def __query_user_session(username: str) -> UserSession:
    """
    Placeholder for creating/retrieving user's session from the DB, including settings and constraints
    """
    session = UserSession(
        user=UserInfo(username, ["ca-edd-web"]),
        chat_engine_settings=ChatEngineSettings("ca-edd-web"),
    )
    logger.info("Found user session for: %s", username)
    return session


async def _get_user_session(username: str) -> UserSession:
    session = __query_user_session(username)
    # Ensure user exists in Literal AI
    literalai_user = await literalai.api.get_or_create_user(username, session.user.__dict__)
    # Set the LiteralAI user ID for this session
    session.literalai_user_id = literalai_user.id
    return session


# endregion
# region: ===================  Example API Endpoint and logging to LiteralAI  ===================


# This will show up as a separate step in LiteralAI, showing input and output
@literalai.step(type="tool")
def list_engines() -> list[str]:
    return chat_engine.available_engines()


# Make sure to use async functions for faster responses
@router.get("/engines")
async def engines(username: str) -> list[str]:
    session = await _get_user_session(username)
    # Example of using Literal AI to log the request and response
    with literalai.thread(name="API:/engines", participant_id=session.literalai_user_id):
        request_msg = literalai.message(
            content="List chat engines",
            type="user_message",
            name=username,
            metadata=session.user.__dict__,
        )
        response = [engine for engine in list_engines() if engine in session.user.allowed_engines]
        # Example of using parent_id to have a hierarchy of messages in Literal AI
        literalai.message(content=str(response), type="system_message", parent_id=request_msg.id)

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
    # May want to cache engine instances rather than creating them for each request
    engine = chat_engine.create_engine(session.chat_engine_settings.engine_id)
    if not engine:
        raise HTTPException(
            status_code=406, detail=f"Unknown engine: {session.chat_engine_settings.engine_id}"
        )
    for setting_name in engine.user_settings:
        if setting_value := getattr(session.chat_engine_settings, setting_name, None):
            setattr(engine, setting_name, setting_value)
    return engine


# curl -X POST 'http://0.0.0.0:8001/query' -H 'Content-Type: application/json' -d '{ "session_id": "12", "new_session": true, "message": "list unemployment insurance benefits?" }'
@router.post("/query")
async def query(request: QueryRequest) -> QueryResponse:
    session = await _get_user_session(request.session_id)
    with literalai.thread(name="API:/query", participant_id=session.literalai_user_id):
        request_msg = literalai.message(
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
        response_msg = literalai.message(
            content=response.response_text,
            type="assistant_message",
            parent_id=request_msg.id,
            metadata={"citations": [c.__dict__ for c in response.citations]},
        )
        # id needed to later provide feedback on this message in LiteralAI
        response.response_id = response_msg.id

    # FIXME: Wait for all steps to be sent. This is NOT needed in production code.
    await literalai.flush()
    return response


async def run_query(engine: ChatEngineInterface, question: str) -> QueryResponse:
    MOCK_RESPONSE = True
    if MOCK_RESPONSE:
        citations = [
            Citation(
                citation_id="citation-1",
                source_id="e4b3050a-23a4-47d6-8634-67012ea1a9d0",
                source_name="Register and Apply for Unemployment Insurance",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/apply/",
                headings=["Register and Apply for Unemployment Insurance"],
                citation_text="[File for unemployment](https://edd.ca.gov/en/unemployment/Filing_a_Claim/) in the first week that you lose your job or have your hours reduced. Your claim begins the Sunday of the week you applied for unemployment.",
            ),
            Citation(
                citation_id="citation-2",
                source_id="e4b3050a-23a4-47d6-8634-67012ea1a9d0",
                source_name="Register and Apply for Unemployment Insurance",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/apply/",
                headings=["Register and Apply for Unemployment Insurance"],
                citation_text="### Benefit Year End Date\nA regular unemployment insurance benefit year ends 12 months after the claim started.",
            ),
            Citation(
                citation_id="citation-3",
                source_id="e4b3050a-23a4-47d6-8634-67012ea1a9d0",
                source_name="Register and Apply for Unemployment Insurance",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/apply/",
                headings=["Register and Apply for Unemployment Insurance"],
                citation_text="You cannot be paid for weeks of unemployment after your benefit year ends, even if you have a balance on your claim. Continue to certify for benefits if you haveweeks available within your benefit year.",
            ),
            Citation(
                citation_id="citation-4",
                source_id="83d89e49-dc9d-4f9f-8bb3-82650e3a3133",
                source_name="Filing an Unemployment Claim",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/Filing_a_Claim/",
                headings=["Filing an Unemployment Claim"],
                citation_text="## Prepare to Apply\nFile for unemployment in the first week that you lose your job or have your hours reduced. Your claim begins the Sunday of the week you applied for unemployment. You must serve a one-week unpaid waiting period on your claim before you are paid unemployment insurance benefits. The waiting period can only be served if you certify for benefits and meet all eligibility requirements for that week. Your first certification will usually include the one-week unpaid waiting period and one week of payment if you meet eligibility requirements for both weeks. **Certify for benefits every two weeks to continue receiving benefit payments**.",
            ),
            Citation(
                citation_id="citation-5",
                source_id="6e0e0cfd-0b44-422b-8af1-119897b8a22d",
                source_name="Unemployment Insurance – After You Apply",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/After_You_Filed/",
                headings=[
                    "Unemployment Insurance – After You Apply",
                    "Unemployment Insurance – After You Apply",
                    "Important Next Steps",
                ],
                citation_text="### Certify for Benefits Every Two Weeks\nTo continue receiving benefits, you must provide [eligibility information](https://edd.ca.gov/en/unemployment/eligibility/) every two weeks. This process is known as [certifying for benefits](https://edd.ca.gov/en/unemployment/ways-to-certify-ui-benefits/). You can do this with [UI Online](https://edd.ca.gov/en/unemployment/ui_online/), [EDD Tele-Cert](https://edd.ca.gov/en/unemployment/EDD_Tele-Cert/), or by mail—whichever is easier for you.",
            ),
            Citation(
                citation_id="citation-6",
                source_id="e4b3050a-23a4-47d6-8634-67012ea1a9d0",
                source_name="Register and Apply for Unemployment Insurance",
                page_number=None,
                uri="https://edd.ca.gov/en/unemployment/apply/",
                headings=["Register and Apply for Unemployment Insurance"],
                citation_text="If you filed for unemployment within the last 52 weeks and have not exhausted your benefits, you must [reopen your claim](https://edd.ca.gov/en/unemployment/reopen-a-claim/) to restart your benefits.",
            ),
        ]
        # from pprint import pformat
        # logger.info(pformat(citations))
        return QueryResponse(
            response_text="Here are some important deadlines for unemployment insurance benefits:\n\n- **Apply Early**: File for unemployment in the first week you lose your job or your hours are reduced. Your claim starts the Sunday of the week you apply.(citation-1)\n- **Benefit Year**: A regular unemployment insurance benefit year ends 12 months after your claim starts. You cannot be paid for weeks of unemployment after your benefit year ends, even if you have a balance on your claim.(citation-2) (citation-3)\n- **Certify Every Two Weeks**: To continue receiving benefits, you must certify for benefits every two weeks. This involves answering questions to confirm you are still eligible.(citation-4) (citation-5)\n- **Reopen Claims**: If you filed for unemployment within the last 52 weeks and haven't exhausted your benefits, you must reopen your claim to restart your benefits.(citation-6)\n\nFor more detailed information, you can visit the EDD website or contact them directly.",
            citations=citations,
        )
    else:
        logger.info("Received: %s", question)
        chat_history = None
        result = await asyncify(lambda: engine.on_message(question, chat_history))()
        logger.info("Response: %s", result.response)

        final_result = simplify_citation_numbers(result)
        citations = [
            Citation.from_subsection(subsection) for subsection in final_result.subsections
        ]
        return QueryResponse(response_text=final_result.response, citations=citations)


# endregion

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # Use port 8001 so that this standalone API app does not conflict with the Chainlit app
    uvicorn.run(router, host="127.0.0.1", port=8001, log_level="info")

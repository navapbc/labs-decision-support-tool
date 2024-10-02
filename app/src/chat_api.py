#!/usr/bin/env python3

"""
This is an initial API that demonstrates how to create an API using FastAPI,
which is compatible with Chainlit. This file is a starting point for creating
an API that can be deployed with the Chainlit chatbot or as a standalone app.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from literalai import AsyncLiteralClient
from pydantic import BaseModel

from src import backend, chat_engine
from src.chat_engine import ChatEngineInterface
from src.db.models.document import ChunkWithScore
from src.healthcheck import HealthCheck, health

if __name__ == "__main__":
    # If running this file directly, define the FastAPI app
    app = FastAPI()
else:
    # Otherwise use Chainlit's app
    # See https://docs.chainlit.io/deploy/api#how-it-works
    from chainlit.server import app

logger = logging.getLogger(__name__)


@app.get("/healthcheck")
async def healthcheck(request: Request) -> HealthCheck:
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


# TODO: Replace with a database query
KNOWN_API_KEYS: dict[str, str] = {}


@app.get("/api_key/{client_name}")
async def create_api_key(client_name: str) -> str:
    "Placeholder for creating an API key for the user"

    # TODO: replace with an database query result
    if not client_name.endswith("doe"):
        raise HTTPException(status_code=401, detail=f"Unauthorized client: {client_name}")

    new_key = str(uuid.uuid4())
    # TODO: Save the new key in the database
    KNOWN_API_KEYS[new_key] = client_name
    return new_key


literalai = AsyncLiteralClient()


@dataclass
class UserInfo:
    client_name: str
    username: str
    email: str
    allowed_engines: list[str]


@dataclass
class ChatEngineSettings:
    id: str
    retrieval_k: int
    retrieval_k_min_score: float


@dataclass
class UserSession:
    user: UserInfo
    chat_engine: ChatEngineSettings
    literalai_user_id: str | None = None


def query_user_session(client_name: str, username: str) -> UserSession:
    """
    Placeholder for creating/retrieving user's session, including settings and constraints
    """
    session = UserSession(
        # TODO: Make allowed_engines configurable
        user=UserInfo(client_name, username, "doe@partner.org", ["bridges-eligibility-manual"]),
        # TODO: Make user settings updatable
        chat_engine=ChatEngineSettings("bridges-eligibility-manual", 8, 0.5),
    )
    logger.info("Found user session for: %s", username)
    return session


async def get_user_session(api_key: str, username: str) -> UserSession:
    # TODO: Replace with a database query
    if api_key not in KNOWN_API_KEYS:
        raise HTTPException(status_code=401, detail=f"Unknown API key: {api_key}")

    session = query_user_session(KNOWN_API_KEYS[api_key], username)
    # Ensure user exists in Literal AI
    literalai_user = await literalai.api.get_or_create_user(username, session.user.__dict__)
    # Set the LiteralAI user ID for this session
    session.literalai_user_id = literalai_user.id
    return session


@literalai.step(type="tool")
def list_engines() -> list[str]:
    return chat_engine.available_engines()


# Make sure to use async functions for faster responses
@app.get("/engines")
async def engines(api_key: str, username: str) -> list[str]:
    session = await get_user_session(api_key, username)
    # Example of using Literal AI to log the request and response, without incurring LLM costs
    # TODO: Simplify since we probably don't need to log this request to Literal AI
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


class QueryRequest(BaseModel):
    api_key: str
    username: str
    message: str


class ChunkResponse(BaseModel):
    text: str
    score: float
    document_name: str
    page_number: Optional[int] | None
    headings: Optional[list[str]] | None

    @staticmethod
    def from_chunk_with_score(scored_chunk: ChunkWithScore) -> "ChunkResponse":
        return ChunkResponse(
            text=scored_chunk.chunk.content,
            score=scored_chunk.score,
            document_name=scored_chunk.chunk.document.name,
            page_number=scored_chunk.chunk.page_number,
            headings=scored_chunk.chunk.headings,
        )


class QueryResponse(BaseModel):
    response: str
    chunks: list[ChunkResponse]
    formatted_response: str

    # id needed to call the feedback endpoint
    step_id: Optional[str] | None = None


@app.post("/query")
async def query(request: QueryRequest) -> QueryResponse:
    session = await get_user_session(request.api_key, request.username)
    with literalai.thread(name="API:/query", participant_id=session.literalai_user_id):
        request_msg = literalai.message(
            content=request.message,
            type="user_message",
            name=request.username,
            metadata=session.user.__dict__,
        )

        # May want to cache engine instances rather than creating them for each request
        engine = chat_engine.create_engine(session.chat_engine.id)
        if not engine:
            raise HTTPException(status_code=406, detail=f"Unknown engine: {session.chat_engine.id}")

        response = await run_query(engine, request.message)

        # Example of using parent_id to have a hierarchy of messages in Literal AI
        response_msg = literalai.message(
            content=str(response.formatted_response),
            type="assistant_message",
            parent_id=request_msg.id,
            # FIXME: metadata=response.__dict__,
        )
        response.thread_id = request_msg.thread_id
        response.step_id = response_msg.id

    # FIXME: Wait for all steps to be sent. This is NOT needed in production code.
    await literalai.flush()
    return response


@literalai.run
async def run_query(engine: ChatEngineInterface, question: str) -> QueryResponse:
    MOCK_RESPONSE = True
    if MOCK_RESPONSE:
        return QueryResponse(
            response="Refugee programs are federal initiatives designed to help refugees become self-sufficient in the United States after their arrival. They include:\n\n- **Refugee Cash Assistance (RCA)** and **Refugee Medical Assistance (RMA)**, which provide financial aid and medical support (citation-0)(citation-2).\n- **Refugee Resettlement Agencies**, which offer services like orientation, counseling, job training, and Matching Grants to assist with economic independence (citation-1).\n- The **Office of Refugee Resettlement (ORR)** oversees these programs, with state agencies managing payment rates and eligibility (citation-2).\n\nThe primary aim is to aid refugees in attaining economic self-sufficiency and integrating into their new communities (citation-3).",
            chunks=[
                ChunkResponse(
                    text="The refugee assistance programs are federal programs which help refugees to become self-sufficient after their arrival in the U.S. Refugee Assistance Program (RAP) has two components; Refugee Cash Assistance(RCA) and Refugee Medical Assistance (RMA).",
                    score=0.7114870548248291,
                    document_name="BEM 630: REFUGEE ASSISTANCE PROGRAM",
                    page_number=1,
                    headings=["DepartmentPhilosophy"],
                ),
                ChunkResponse(
                    text="Refugee Resettlement Agencies also known as Voluntary Agencies (VOLAGs) may provide the following services:\n- Reception and placement services to newly arrived refugees including orientation, counseling, resettlement grants, translation/interpretation, and related services.\n- Employability services such as English language instruction, transportation, child care, citizenship and employment authorization document assistance, translation/interpretation, and related services.\n- Matching Grants (MG) to help refugees attain economic self- sufficiency without accessing public cash assistance.",
                    score=0.654638409614563,
                    document_name="BEM 630: REFUGEE ASSISTANCE PROGRAM",
                    page_number=2,
                    headings=["Program administration", "Refugee Resettlement Agencies"],
                ),
                ChunkResponse(
                    text="**The refugee assistance programs** were established by the U.S. Congress. The Office of Refugee Resettlement (ORR) in HHS has specific responsibility for the administration of Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA). The Michigan Department of Labor and Economic Opportunity’s (LEO) Office of Global Michigan administers the programs and sets payment rates and eligibility criteria.",
                    score=0.6306811571121216,
                    document_name="BEM 100: INTRODUCTION",
                    page_number=4,
                    headings=["Refugee Assistance Programs"],
                ),
                ChunkResponse(
                    text="The refugee assistance programs provide financial assistance and medical aid to persons admitted into the U.S. as refugees. Eligibility is also available to certain other non-U.S. citizens with specified immigration statuses, identified in the section refugees in BEM 630.\n\nThe Immigration and Nationality Act, the Code of Federal Regula- tions (CFR), and federal court orders are the legal base for policies and procedures for RCA and RMA and are cited in the applicable manualitem.\n\nThe Child Development and Care (CDC) program provides financial assistance with child care expenses to qualifying families.\n\nThe goal of the CDC program is to support low-income families by providing access to high-quality, affordable, and accessible early learning and development opportunities and to assist the familyin achieving economic independence and self-sufficiency.\n\nState Disability Assistance (SDA) provides financial assistance to disabled adults who are not eligible for FIP. The goal of the SDA program is to provide financial assistance to meet a disabled person's basic personal and shelter needs.",
                    score=0.619068443775177,
                    document_name="BEM 100: INTRODUCTION",
                    page_number=4,
                    headings=["Refugee Assistance Programs", "Program Goal"],
                ),
            ],
            formatted_response='Refugee programs are federal initiatives designed to help refugees become self-sufficient in the United States after their arrival. They include:\n\n- **Refugee Cash Assistance (RCA)** and **Refugee Medical Assistance (RMA)**, which provide financial aid and medical support <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=1\'>1</a>&nbsp;</sup><sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>2</a>&nbsp;</sup>.\n- **Refugee Resettlement Agencies**, which offer services like orientation, counseling, job training, and Matching Grants to assist with economic independence <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=2\'>3</a>&nbsp;</sup>.\n- The **Office of Refugee Resettlement (ORR)** oversees these programs, with state agencies managing payment rates and eligibility <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>2</a>&nbsp;</sup>.\n\nThe primary aim is to aid refugees in attaining economic self-sufficiency and integrating into their new communities <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>4</a>&nbsp;</sup>.<h3>Source(s)</h3>\n        <div class="usa-accordion" id=accordion-659596>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n      class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-659596">\n                    1. BEM 630: REFUGEE ASSISTANCE PROGRAM\n                </button>\n            </h4>\n            <div id="a-659596" class="usa-accordion__content usa-prose" hidden>\n        <p>Department Philosophy</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">The refugee assistance programs are federal programs which help refugees to become self-sufficient after their arrival in the U.S. Refugee Assistance Program (RAP) has two components; Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA).</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=1\'>Open document to page 1</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-659597>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n              aria-controls="a-659597">\n                    2. BEM 100: INTRODUCTION\n                </button>\n            </h4>\n            <div id="a-659597" class="usa-accordion__content usa-prose" hidden>\n                <p>Refugee Assistance Programs</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">**The refugee assistance programs** were established by the U.S. Congress. The Office of Refugee Resettlement (ORR) in HHS has specific responsibility for the administration of Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA). The Michigan Department of Labor and Economic Opportunity’s (LEO) Office of Global Michigan administers the programs and sets payment rates and eligibility criteria.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>Open document to page 4</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-659598>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-659598">\n                    3. BEM 630: REFUGEE ASSISTANCE PROGRAM\n              </button>\n            </h4>\n            <div id="a-659598" class="usa-accordion__content usa-prose" hidden>\n                <p>Program administration → Refugee Resettlement Agencies</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">Refugee Resettlement Agenciesalso known as Voluntary Agencies (VOLAGs) may provide the following services:\n- Reception and placement services to newly arrived refugees including orientation, counseling, resettlement grants, translation/interpretation, and related services.\n- Employability services such as English language instruction, transportation, childcare, citizenship and employment authorization document assistance, translation/interpretation, and related services.\n- Matching Grants (MG) to help refugees attaineconomic self- sufficiency without accessing public cash assistance.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=2\'>Open document to page 2</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-659599>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-659599">\n                    4. BEM 100: INTRODUCTION\n                </button>\n            </h4>\n            <div id="a-659599" class="usa-accordion__content usa-prose" hidden>\n                <p>Refugee Assistance Programs → Program Goal</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">The refugee assistance programs provide financial assistance and medical aid to persons admitted into the U.S. as refugees. Eligibility is also available to certain other non-U.S. citizens with specified immigration statuses, identified in the section refugees in <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf">BEM 630</a>.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>Open document to page 4</a></p>\n            </div>\n        </div>',
        )
    else:
        # TODO: replace formatted_answer with one created by a formatter suitable for the API client
        (result, formatted_answer) = await backend.run_engine(engine, question)

        # from src.chat_engine import OnMessageResult
        # from src.db.models.document import Chunk, Document
        # result = OnMessageResult(
        #     response="My answer.",
        #     chunks_with_scores=[
        #         ChunkWithScore(chunk=Chunk(
        #             document=Document(name="doc1", content="Bridges Eligibility Manual", dataset="bridges-eligibility-manual", program="Bridges", region="Michigan"),
        #             content="chunk_text content",
        #             page_number=2,
        #             headings=["H1"],
        #             num_splits=1,
        #             split_index=0,
        #         ), score=0.9)
        #     ]
        # )
        # formatted_answer = "My answer.\n- point 1\n- point 2\n- point 3\n- point 4\n- point 5\n- point 6"

        return QueryResponse(
            response=result.response,
            chunks=[
                ChunkResponse.from_chunk_with_score(chunk_with_score)
                for chunk_with_score in result.chunks_with_scores
            ],
            formatted_response=str(formatted_answer),
        )


@app.post("/query_html")
async def query_html(request: QueryRequest) -> HTMLResponse:
    response = await query(request)
    return HTMLResponse(format_to_html(response.formatted_response))


@literalai.step(type="tool")
def format_to_html(markdown_response: str) -> str:
    return markdown.markdown(markdown_response)


class FeedbackRequest(BaseModel):
    api_key: str
    username: str

    step_id: str
    score: float
    comment: str


@app.post("/feedback")
async def feedback(request: FeedbackRequest) -> str:
    session = await get_user_session(request.api_key, request.username)
    # API endpoint to send feedback https://docs.literalai.com/guides/logs#add-a-score
    await literalai.api.create_score(
        step_id=request.step_id,
        name=session.user.username,
        type="HUMAN",
        value=request.score,
        comment=request.comment,
    )
    return "Logged"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="127.0.0.1", port=8001, log_level="info")

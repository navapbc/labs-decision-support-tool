#!/usr/bin/env python3

"""
This is an initial API that demonstrates how to create an API using FastAPI,
which is compatible with Chainlit. This file is a starting point for creating
an API that can be deployed with the Chainlit chatbot or as a standalone app.
"""

import logging
import os
import uuid
from dataclasses import dataclass

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from literalai import AsyncLiteralClient
from pydantic import BaseModel

from src import backend, chat_engine
from src.chat_engine import ChatEngineInterface
from src.db.models.document import ChunkWithScore
from src.healthcheck import health, HealthCheck

if __name__ == "__main__":
    # If running directly, define the FastAPI app
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


KNOWN_API_KEYS: dict[str, str] = {}


@app.get("/api_key/{client_name}")
async def create_api_key(client_name: str) -> str:
    "Placeholder for creating an API key for the user"

    # TODO: replace with an SqlAlchemy query result
    if not client_name.endswith("doe"):
        raise HTTPException(status_code=401, detail=f"Unknown user: {client_name}")

    new_key = str(uuid.uuid4())
    KNOWN_API_KEYS[new_key] = client_name
    return new_key


literalai_key = os.environ.get("LITERAL_API_KEY")
literalai = AsyncLiteralClient(api_key=literalai_key, disabled=not bool(literalai_key))


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
        user=UserInfo(client_name, username, "doe@partner.org", ["bridges-eligibility-manual"]),
        chat_engine=ChatEngineSettings("bridges-eligibility-manual", 8, 0.5),
    )
    logger.info("Found user session for: %s", username)
    return session


async def get_user_session(api_key: str, username: str) -> UserSession:
    # Placeholder for validating API key
    if api_key not in KNOWN_API_KEYS:
        raise HTTPException(status_code=401, detail=f"Unknown API key: {api_key}")

    session = query_user_session(KNOWN_API_KEYS[api_key], username)
    # Ensure user exists in Literal AI
    literalai_user = await literalai.api.get_or_create_user(username, session.user.__dict__)
    session.literalai_user_id = literalai_user.id
    print("LiteralAI User ID:", session.literalai_user_id)
    return session


@literalai.step(type="tool")
def list_engines() -> list[str]:
    return chat_engine.available_engines()


# Make sure to use async functions for faster responses
@app.get("/engines")
async def engines(api_key: str, username: str) -> list[str]:
    session = await get_user_session(api_key, username)
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
    page_number: int | None
    headings: list[str] | None

    def __init__(self, scored_chunk: ChunkWithScore):
        self.text = scored_chunk.chunk.content
        self.score = scored_chunk.score
        self.document_name = scored_chunk.chunk.document.name
        self.page_number = scored_chunk.chunk.page_number
        self.headings = scored_chunk.chunk.headings


class QueryResponse(BaseModel):
    response: str
    chunks: list[ChunkResponse]
    formatted_response: str


# To test:
# http://0.0.0.0:8001/docs
# curl -X POST "http://localhost:8001/query" -d '{"api_key": "anything", "username":"jdoe", "message": "My question"}' -H "Content-Type: application/json"
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
        literalai.message(
            content=str(response.formatted_response),
            type="assistant_message",
            parent_id=request_msg.id,
            metadata=response.__dict__,
        )

    # FIXME: Wait for all steps to be sent. This is NOT needed in production code.
    await literalai.flush()
    return response


@literalai.run
async def run_query(engine: ChatEngineInterface, question: str) -> QueryResponse:
    # return QueryResponse(
    #     response="Refugee programs are designed to help refugees become self-sufficient after they arrive in the U.S. Here are some key points about these programs:\n\n- They include Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA) (citation-0).\n- The Office of Refugee Resettlement (ORR) administers these programs, while in Michigan, the Office of Global Michigan handles them (citation-2).\n- Refugee Resettlement Agencies provide services like orientation, counseling, English language instruction, and assistance with employment authorizations (citation-1).\n- Refugees can receive payments directly or have payments made on their behalf to third parties for necessities like rent and utilities (citation-4)(citation-5).\n- Refugees can participate in matching grant programs that focus on job training and maintenance assistance to help them become economically self-sufficient (citation-20).",
    #     chunks_with_scores="[ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45550>, score=0.7413949966430664), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc459a0>, score=0.6745662689208984), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc459d0>, score=0.6454465389251709), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45a00>, score=0.6299465298652649), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45a30>, score=0.6249987483024597), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45a60>, score=0.619025707244873), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45a90>, score=0.617834746837616), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45ac0>, score=0.6155949831008911), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45af0>,score=0.6079249978065491), ChunkWithScore(chunk=<src.db.models.document.Chunk object at 0x30cc45b20>, score=0.5994702577590942)]",
    #     formatted_response='Refugee programs are designed to help refugees become self-sufficient after they arrive in the U.S. Here are some key points about these programs:\n\n- They include Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA) <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=1\'>1</a>&nbsp;</sup>.\n- The Office of Refugee Resettlement (ORR) administers these programs, while in Michigan, the Office of Global Michigan handles them <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>2</a>&nbsp;</sup>.\n- Refugee Resettlement Agencies provide services like orientation, counseling, English language instruction, andassistance with employment authorizations <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=2\'>3</a>&nbsp;</sup>.\n- Refugees can receive payments directly or have payments made on their behalf to third parties for necessities like rent and utilities <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=19\'>4</a>&nbsp;</sup><sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=19\'>5</a>&nbsp;</sup>.\n- Refugees can participate in matching grant programs that focus on job training and maintenance assistance to help them become economically self-sufficient <sup><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=18\'>6</a>&nbsp;</sup>.<h3>Source(s)</h3>\n        <div class="usa-accordion" id=accordion-876904>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n  aria-expanded="false"\n                    aria-controls="a-876904">\n                    1. BEM 630: REFUGEE ASSISTANCE PROGRAM\n                </button>\n         </h4>\n            <div id="a-876904" class="usa-accordion__content usa-prose" hidden>\n                <p>Department Philosophy</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">The refugee assistance programs are federal programs which help refugees to become self-sufficient after their arrival in the U.S. Refugee Assistance Program (RAP) has two components; Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA).</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=1\'>Open document to page 1</a></p>\n            </div>\n        </div>\n       <div class="usa-accordion" id=accordion-876905>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-876905">\n      2. BEM 100: INTRODUCTION\n                </button>\n            </h4>\n            <div id="a-876905" class="usa-accordion__content usa-prose" hidden>\n             <p>Refugee Assistance Programs</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">**The refugee assistance programs** were established by the U.S. Congress. The Office of Refugee Resettlement (ORR) in HHS has specific responsibility for the administration of Refugee Cash Assistance (RCA) and Refugee Medical Assistance (RMA). The Michigan Department of Labor and Economic Opportunity’s (LEO) Office of Global Michigan administers the programs and sets payment rates and eligibility criteria.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/100.pdf#page=4\'>Open document to page 4</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-876906>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                  aria-controls="a-876906">\n                    3. BEM 630: REFUGEE ASSISTANCE PROGRAM\n                </button>\n            </h4>\n            <div id="a-876906" class="usa-accordion__content usa-prose" hidden>\n                <p>Program administration → Refugee Resettlement Agencies</p>\n <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">Refugee Resettlement Agencies also known as Voluntary Agencies (VOLAGs) may provide the following services:\n- Reception and placement services to newly arrived refugees including orientation, counseling, resettlement grants, translation/interpretation, and related services.\n- Employability services such as English language instruction, transportation, child care, citizenship and employment authorization document assistance, translation/interpretation, and related services.\n- Matching Grants (MG) to help refugees attain economic self- sufficiency without accessing public cashassistance.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/630.pdf#page=2\'>Open document to page 2</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-876907>\n            <h4 class="usa-accordion__heading">\n                <button\n     type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-876907">\n                    4. BEM 503: INCOME, UNEARNED\n                </button>\n            </h4>\n            <div id="a-876907" class="usa-accordion__content usa-prose" hidden>\n                <p>GOVERNMENT AID → Refugee Resettlement Assistance</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">Refugee resettlement assistance is distributed within 90 days of a refugee’s date of entry. Payments may be made to third parties such as landlords, utility companies or other service providers: see Third Party Assistance in <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/500.pdf">BEM 500</a>.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=19\'>Open document to page 19</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-876908>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n                    class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-876908">\n        5. BEM 503: INCOME, UNEARNED\n                </button>\n            </h4>\n            <div id="a-876908" class="usa-accordion__content usa-prose" hidden>\n                <p>GOVERNMENT AID → Refugee Resettlement Assistance</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">Payments may also be made directly to refugees. The number and frequency of payments are determined by the refugee resettlement agency.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=19\'>Open document to page 19</a></p>\n            </div>\n        </div>\n        <div class="usa-accordion" id=accordion-876909>\n            <h4 class="usa-accordion__heading">\n                <button\n                    type="button"\n      class="usa-accordion__button"\n                    aria-expanded="false"\n                    aria-controls="a-876909">\n                    6. BEM 503: INCOME, UNEARNED\n                </button>\n            </h4>\n            <div id="a-876909" class="usa-accordion__content usa-prose" hidden>\n                <p>GOVERNMENT AID → Refugee Matching Grant</p>\n                <div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">This is an employment program administered by refugee resettle- ment agencies. It provides job training and maintenance assistance (food, housing, transportation, etc.) to eligible refugees. The benefits are partly cash, but mainly in-kind goods and services. Enter any cash payments made directly to the refugee in the unearned income logical unit of work.</div>\n                <p><a href=\'https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/503.pdf#page=18\'>Open document to page 18</a></p>\n            </div>\n        </div>',
    # )

    # TODO: replace formatted_answer with one created by a formatter suitable for the API client
    (result, formatted_answer) = await backend.run_engine(engine, question)

    return QueryResponse(
        response=result.response,
        chunks=[ChunkResponse(chunk_with_score) for chunk_with_score in result.chunks_with_scores],
        formatted_response=str(formatted_answer),
    )


@literalai.step(type="tool")
def format_to_html(markdown_response: str) -> str:
    return markdown.markdown(markdown_response)


@app.post("/query_html")
async def query_html(request: QueryRequest) -> HTMLResponse:
    response = await query(request)
    return HTMLResponse(format_to_html(response.formatted_response))


# TODO: API to send feedback; https://docs.literalai.com/guides/logs#add-a-score


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=8001, log_level="info")

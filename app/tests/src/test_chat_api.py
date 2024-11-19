import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from src import chat_api
from src.chat_api import (
    ChatEngineSettings,
    QueryResponse,
    UserInfo,
    UserSession,
    get_chat_engine,
    router,
    run_query,
)
from src.chat_engine import OnMessageResult
from src.citations import CitationFactory, split_into_subsections
from tests.src.db.models.factories import ChunkFactory


def mock_literalai():
    @contextmanager
    def dummy_context_manager():
        yield

    mock = MagicMock()
    mock.thread.return_value = dummy_context_manager()
    mock.step.return_value = dummy_context_manager()
    return mock


@pytest.fixture
def client(monkeypatch):
    mock = mock_literalai()
    monkeypatch.setattr(mock, "api", AsyncMock())
    monkeypatch.setattr(chat_api, "literalai", lambda: mock)
    return TestClient(router)


def test_api_healthcheck(client):
    response = client.get("/api/healthcheck")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_api_engines(client):
    response = client.get("/api/engines?user_id=TestUser")
    assert response.status_code == 200
    assert response.json() == ["ca-edd-web"]


def test_api_query(monkeypatch, client):
    async def mock_run_query(engine, question):
        return QueryResponse(
            response_text="Response from LLM",
            citations=[],
        )

    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)

    response = client.post(
        "/api/query", json={"session_id": "Session0", "new_session": True, "message": "Hello"}
    )
    assert response.status_code == 200
    assert response.json()["response_text"] == "Response from LLM"


def test_api_query__bad_request(client):
    try:
        client.post("/api/query", json={"session_id": "Session0", "new_session": True})
    except RequestValidationError as e:
        error = e.errors()[0]
        assert error["type"] == "missing"
        assert error["msg"] == "Field required"
        assert error["loc"] == ("body", "message")


@pytest.fixture
def subsections():
    # Provide a factory to reset the citation id counter
    return split_into_subsections(ChunkFactory.build_batch(3), factory=CitationFactory())


@pytest.mark.asyncio
async def test_run_query__1_citation(subsections):
    class MockChatEngine:
        def on_message(self, question, chat_history):
            return OnMessageResult(
                "Response from LLM (citation-2)", "Some system prompt", [], subsections
            )

    query_response = await run_query(MockChatEngine(), "My question")
    assert query_response.response_text == "Response from LLM (citation-1)"
    assert len(query_response.citations) == 1
    assert query_response.citations[0].citation_id == "citation-1"


@pytest.mark.asyncio
async def test_run_query__2_citations(subsections):
    class MockChatEngine:
        def on_message(self, question, chat_history):
            return OnMessageResult(
                "Response from LLM (citation-2)(citation-3)", "Some system prompt", [], subsections
            )

    query_response = await run_query(MockChatEngine(), "My question")
    assert query_response.response_text == "Response from LLM (citation-1)(citation-2)"
    assert len(query_response.citations) == 2
    assert query_response.citations[0].citation_id == "citation-1"
    assert query_response.citations[1].citation_id == "citation-2"


@pytest.mark.asyncio
async def test_run_query__unknown_citation(subsections, caplog):
    class MockChatEngine:
        def on_message(self, question, chat_history):
            return OnMessageResult(
                "Response from LLM (citation-2)(citation-44)", "Some system prompt", [], subsections
            )

    with caplog.at_level(logging.ERROR):
        query_response = await run_query(MockChatEngine(), "My question")
        assert any(
            text == "LLM generated a citation for a reference (citation-44) that doesn't exist."
            for text in caplog.messages
        )

    assert query_response.response_text == "Response from LLM (citation-1)"
    assert len(query_response.citations) == 1
    assert query_response.citations[0].citation_id == "citation-1"


@pytest.fixture
def user_info():
    return UserInfo("TestUser", ["ca-edd-web"])


def test_get_chat_engine(user_info):
    session = UserSession(
        user=user_info,
        chat_engine_settings=ChatEngineSettings("ca-edd-web", retrieval_k=6),
    )
    engine = get_chat_engine(session)
    assert engine.retrieval_k == 6


def test_get_chat_engine__unknown(user_info):
    session = UserSession(
        user=user_info,
        chat_engine_settings=ChatEngineSettings("engine_y"),
    )
    with pytest.raises(HTTPException, match="Unknown engine: engine_y"):
        get_chat_engine(session)


def test_get_chat_engine_not_allowed(user_info):
    session = UserSession(
        user=user_info,
        chat_engine_settings=ChatEngineSettings("bridges-eligibility-manual"),
    )
    with pytest.raises(HTTPException, match="Unknown engine: bridges-eligibility-manual"):
        get_chat_engine(session)

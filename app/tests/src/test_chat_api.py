import logging
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from literalai import Score

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
from src.chat_engine import ImagineLA_MessageAttributes, OnMessageResult
from src.citations import CitationFactory, split_into_subsections
from src.generate import MessageAttributes
from tests.src.db.models.factories import ChunkFactory


class MockContextManager:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def mock_literalai():
    mock = MagicMock()
    mock.thread.return_value = MockContextManager()
    mock.step.return_value = MockContextManager()
    return mock


@pytest.fixture
def client(monkeypatch):
    mock = mock_literalai()
    monkeypatch.setattr(mock, "api", AsyncMock())
    monkeypatch.setattr(chat_api, "literalai", lambda: mock)
    return TestClient(router)


class MockLiteralAIApi:
    async def get_or_create_user(self, identifier, metadata):
        self.id = identifier
        return self

    async def create_score(
        self,
        name: str | None,
        type: str,
        value: float,
        step_id: Optional[str] = None,
        comment: Optional[str] = None,
    ):
        return Score(
            name=name,
            type=type,
            value=value,
            step_id=step_id,
            comment=comment,
            generation_id=None,
            dataset_experiment_item_id=None,
            tags=None,
        )


@pytest.fixture
def literalai_client(monkeypatch):
    mock = mock_literalai()
    monkeypatch.setattr(mock, "api", MockLiteralAIApi())
    monkeypatch.setattr(chat_api, "literalai", lambda: mock)

    return TestClient(router)


def test_api_engines(client):
    response = client.get("/api/engines?user_id=TestUser")
    assert response.status_code == 200
    assert response.json() == ["imagine-la"]


def test_api_query(monkeypatch, client):
    async def mock_run_query(engine, question, chat_history):
        return QueryResponse(
            response_text=f"Response from LLM: {chat_history}",
            citations=[],
        )

    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)

    response = client.post(
        "/api/query", json={"session_id": "Session0", "new_session": True, "message": "Hello"}
    )
    assert response.status_code == 200
    assert response.json()["response_text"] == "Response from LLM: []"

    # Posting again with the same session_id should fail
    try:
        client.post(
            "/api/query",
            json={"session_id": "Session0", "new_session": True, "message": "Hello again"},
        )
        raise AssertionError("Expected HTTPException")
    except HTTPException as e:
        assert e.status_code == 409
        assert e.detail == "Cannot start a new session with existing session_id: Session0"

    # Test chat history
    response = client.post(
        "/api/query",
        json={"session_id": "Session0", "new_session": False, "message": "Hello again"},
    )
    assert response.status_code == 200
    assert (
        response.json()["response_text"]
        == "Response from LLM: [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Response from LLM: []'}]"
    )


def test_api_query__nonexistent_session_id(monkeypatch, client):
    try:
        client.post(
            "/api/query",
            json={"session_id": "NewSession999", "new_session": False, "message": "Should fail"},
        )
        raise AssertionError("Expected HTTPException")
    except HTTPException as e:
        assert e.status_code == 409
        assert e.detail == "Chat history for existing session not found: NewSession999"


def test_api_query__bad_request(client):
    try:
        client.post("/api/query", json={"session_id": "Session0", "new_session": True})
        raise AssertionError("Expected RequestValidationError")
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
                "Response from LLM (citation-2)",
                "Some system prompt",
                MessageAttributes(needs_context=True, translated_message=""),
                chunks_with_scores=[],
                subsections=subsections,
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
                "Response from LLM (citation-2)(citation-3)",
                "Some system prompt",
                ImagineLA_MessageAttributes(
                    needs_context=True,
                    translated_message="",
                    canned_response="",
                    alert_message="Some alert message.",
                ),
                chunks_with_scores=[],
                subsections=subsections,
            )

    query_response = await run_query(MockChatEngine(), "My question")
    assert (
        query_response.alert_message
        == "**Policy update**: Some alert message.\n\nThe rest of this answer may be outdated."
    )
    assert (
        query_response.response_text
        == f"{query_response.alert_message}\n\nResponse from LLM (citation-1)(citation-2)"
    )
    assert len(query_response.citations) == 2
    assert query_response.citations[0].citation_id == "citation-1"
    assert query_response.citations[1].citation_id == "citation-2"


@pytest.mark.asyncio
async def test_run_query__unknown_citation(subsections, caplog):
    class MockChatEngine:
        def on_message(self, question, chat_history):
            return OnMessageResult(
                "Response from LLM (citation-2)(citation-44)",
                "Some system prompt",
                MessageAttributes(needs_context=True, translated_message=""),
                chunks_with_scores=[],
                subsections=subsections,
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


def test_post_feedback_success(literalai_client):
    response = literalai_client.post(
        "/api/feedback",
        json={
            "session_id": "Session2",
            "is_positive": "true",
            "response_id": "response_id0",
            "comment": "great answer",
        },
    )

    assert response.status_code == 200


def test_post_feedback_fail(monkeypatch, literalai_client):
    try:
        literalai_client.post(
            "/api/feedback",
            json={
                "session_id": "Session2",
                "is_positive": "true",
                "comment": "great answer",
            },
        )
        raise AssertionError("Expected RequestValidationError")
    except RequestValidationError as e:
        error = e.errors()[0]
        assert error["type"] == "missing"
        assert error["msg"] == "Field required"
        assert error["loc"] == ("body", "response_id")

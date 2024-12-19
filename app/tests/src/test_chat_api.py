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
    Citation,
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


def test_citation_formatting():
    subsection_text = "* [CalFresh](https://www.getcalfresh.org/?source=edd) (formerly known as Food Stamps)  \n  CalFresh provides monthly food assistance to people and families with low income, including those who lost their job because of the pandemic. Visit [GetCalFresh.org](https://www.getcalfresh.org/?source=edd) to apply online.\n* [California Association of Food Banks](http://www.cafoodbanks.org/)  \n  In California, federal, state, and local community organizations coordinate to make sure that groceries are available at local food banks.\n* [Free Summer Lunch Programs](http://www.cde.ca.gov/ds/sh/sn/summersites.asp)  \n  Free lunches are available to all children under 18, regardless of income.\n* [School Meals](https://www.fns.usda.gov/school-meals/applying-free-and-reduced-price-school-meals)  \n  Free or reduced-price breakfast and lunch at public schools when in session.\n* [Women, Infants and Children (WIC) Program](https://www.cdph.ca.gov/Programs/CFH/DWICSN/Pages/Program-Landing1.aspx)  \n  Pregnant women and children under age 5 receive nutrition support at WIC."
    source_url = "https://edd.ca.gov/en/disability/options_to_file_for_pfl_benefits/"
    highlighted_url = Citation.format_highlighted_uri(source_url, subsection_text)
    assert "*" not in highlighted_url
    assert " " not in highlighted_url
    assert (
        highlighted_url
        == "https://edd.ca.gov/en/about_edd/additional_resources#:~:text=CalFresh%20https%20www%20getcalfresh%20org,receive%20nutrition%20support%20at%20WIC"
    )

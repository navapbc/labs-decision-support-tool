import asyncio
import logging
import threading
from contextlib import contextmanager
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from literalai import Score
from literalai.observability.step import ScoreType

from chainlit import data as cl_data
from src import chainlit_data, chat_api
from src.chat_api import (
    ChatEngineSettings,
    ChatSession,
    QueryResponse,
    get_chat_engine,
    router,
    run_query,
)
from src.chat_engine import ImagineLA_MessageAttributes, OnMessageResult
from src.citations import CitationFactory, split_into_subsections
from src.generate import MessageAttributes
from tests.src.db.models.factories import ChunkFactory, UserSessionFactory


@contextmanager
def mockContextManager():
    yield


class MockLiteralAI:
    def __init__(self):
        self.api = MockLiteralAIApi()

    def thread(self, *args, **kwargs):
        return mockContextManager()

    def step(self, *args, **kwargs):
        return mockContextManager()

    def message(self, *args, **kwargs):
        mock_msg = MagicMock()
        mock_msg.thread_id = "12345"
        return mock_msg


class MockLiteralAIApi:
    async def get_or_create_user(self, identifier, metadata):
        self.id = f"litai_uuid_for_{identifier}"
        # include await call to yield control back to the event loop
        await asyncio.sleep(0)
        return self

    async def create_score(
        self,
        name: str,
        type: ScoreType,
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
            dataset_experiment_item_id=None,
            tags=None,
        )


@pytest.fixture
def mock_lai(monkeypatch):
    # Set LITERAL_API_KEY to create a secondary data layer
    monkeypatch.setenv("LITERAL_API_KEY", "")
    # Create a no-op mock for the secondary data layer
    monkeypatch.setattr(chainlit_data, "get_literal_data_layer", lambda _key: AsyncMock())

    monkeypatch.setattr(chat_api, "literalai", lambda: MockLiteralAI())


@pytest.fixture
def client(mock_lai, db_session):  # mock LiteralAI when testing API
    return TestClient(router)


@pytest.fixture
def async_client(mock_lai, db_session):  # mock LiteralAI when testing API
    """
    The typical FastAPI TestClient creates its own event loop to handle requests,
    which led to issues when testing code that relies on asynchronous operations
    or resources tied to an event loop (i.e., ContextVars).
    To address errors like "RuntimeError: Task attached to a different loop",
    make tests asynchronous and directly use httpx.AsyncClient to work within the same event loop context.
    """
    reset_cl_data_layer()
    return AsyncClient(transport=ASGITransport(app=router), base_url="http://test")


def reset_cl_data_layer():
    """
    Async unit tests can run in different event loops.
    There is one FastAPI router used for all tests in this file.
    In chat_api.py when the router calls get_data_layer(), the data layer is created in a test's event loop.
    When get_data_layer() is called again in a different event loop (in a different async unit test), it raises an error:
    'asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress'
    because chainlit.data.chainlit_data_layer initializes using asyncpg.create_pool() in the first event loop,
    and that connection pool is available only in the same event loop.
    "This is by design and cannot be changed. If you change your loop between tests, make sure you do not reuse any pools or connections."
    https://github.com/MagicStack/asyncpg/issues/293#issuecomment-391157754
    Running a single test passes, but running all tests in this file fails.
    This only affects tests, where the router functions are called by the test client, as opposed to sending HTTP requests.

    TLDR: chat_api uses chainlit_data_layer, which uses asyncpg, which is tied to the event loop.
    Since tests can run in different event loops, we need to reset the chainlit_data_layer between tests.

    Alternative 1: to create a new FastAPI router for each test but router is referenced in many places
        (including API endpoints setup) so some references may point to the original router.
    Alternative 2: use one event loop for all tests -- https://github.com/pytest-dev/pytest-asyncio/issues/924#issuecomment-2328433273.
    Alternative 3: Create a asyncio.new_event_loop(), asyncio.set_event_loop(new_loop),
        new_loop.run_until_complete(_cause_asyncpg_create_pool()), and new_loop.run_until_complete(_my_test())
    """
    cl_data._data_layer = None
    cl_data._data_layer_initialized = False


def test_api_engines(client):
    response = client.get("/api/engines?user_id=TestUser")
    assert response.status_code == 200
    assert response.json() == ["imagine-la"]


@pytest.mark.asyncio
async def test_api_engines__dbsession_contextvar(async_client, monkeypatch):
    event = threading.Event()
    db_sessions = []

    async def waiting_get_or_create_user(_self, identifier, _metadata):
        db_session = chat_api.dbsession.get()
        db_sessions.append(db_session)
        print("Waiting for event.set() ...", db_session)
        # Run the blocking wait in a separate thread to avoid blocking the event loop
        await asyncio.to_thread(event.wait)

        mock_user = MagicMock()
        mock_user.id = f"litai_uuid_for_{identifier}"
        return mock_user

    monkeypatch.setattr(MockLiteralAIApi, "get_or_create_user", waiting_get_or_create_user)

    async def checker_coroutine():
        while len(db_sessions) < 2:
            print("Checker coroutine waiting for other tasks to add to dbsessions")
            # Allow the event loop to run other tasks
            await asyncio.sleep(0.1)
        print("Checker coroutine event.set()")
        # Wake up the waiting threads to let the API resume responding
        event.set()

    async with async_client:
        call1 = async_client.get("/api/engines?user_id=TestUser1")
        call2 = async_client.get("/api/engines?user_id=TestUser2")
        checker = checker_coroutine()

        tasks = [asyncio.create_task(call) for call in [call1, call2, checker]]
        results = await asyncio.gather(*tasks)
        assert [r.status_code for r in results if r] == [200, 200]

    # chat_api.dbsession.get() should be distinct for each thread
    assert len(set(db_sessions)) == 2

    # Ensure all other asyncio tasks are done
    pending_tasks = [task for task in asyncio.all_tasks() if not task.done()]
    assert len(pending_tasks) == 1


def test_api_query(monkeypatch, client):
    async def mock_run_query(engine, question, chat_history):
        return (
            QueryResponse(
                response_text=f"Response from LLM: {chat_history}",
                citations=[],
            ),
            {},
        )

    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)

    response = client.post(
        "/api/query",
        json={
            "user_id": "user9",
            "session_id": "Session0",
            "new_session": True,
            "message": "Hello",
        },
    )
    assert response.status_code == 200
    assert response.json()["response_text"] == "Response from LLM: []"

    # Posting again with the same session_id should fail
    try:
        client.post(
            "/api/query",
            json={
                "user_id": "user9",
                "session_id": "Session0",
                "new_session": True,
                "message": "Hello again",
            },
        )
        raise AssertionError("Expected HTTPException")
    except HTTPException as e:
        assert e.status_code == 409
        assert (
            e.detail
            == "Cannot start a new session 'Session0' that is already associated with thread_id '12345'"
        )

    # Test chat history
    response = client.post(
        "/api/query",
        json={
            "user_id": "user9",
            "session_id": "Session0",
            "new_session": False,
            "message": "Hello again",
        },
    )
    assert response.status_code == 200
    assert (
        response.json()["response_text"]
        == "Response from LLM: [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Response from LLM: []'}]"
    )


"""
def test_api_query__empty_user_id(monkeypatch, client):
    try:
        client.post(
            "/api/query",
            json={
                "user_id": "",
                "session_id": "NewSession999",
                "new_session": False,
                "message": "Should fail",
            },
        )
        raise AssertionError("Expected RequestValidationError")
    except RequestValidationError as e:
        error = e.errors()[0]
        assert error["type"] == "string_too_short"
        assert error["msg"] == "String should have at least 1 character"
        assert error["loc"] == ("body", "user_id")
"""


def test_api_query__nonexistent_session_id(monkeypatch, client):
    try:
        client.post(
            "/api/query",
            json={
                "user_id": "user8",
                "session_id": "NewSession999",
                "new_session": False,
                "message": "Should fail",
            },
        )
        raise AssertionError("Expected HTTPException")
    except HTTPException as e:
        assert e.status_code == 409
        assert e.detail == "LiteralAI thread ID for existing session 'NewSession999' not found"


def test_api_query__bad_request(client):
    try:
        client.post(
            "/api/query", json={"user_id": "user7", "session_id": "Session0", "new_session": True}
        )
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

    query_response, metadata = await run_query(MockChatEngine(), "My question")
    assert query_response.response_text == "Response from LLM (citation-1)"
    assert len(query_response.citations) == 1
    assert query_response.citations[0].citation_id == "citation-1"

    assert metadata["attributes"]["needs_context"] is True


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
                    benefit_program="CalFresh",
                    canned_response="",
                    alert_message="**Policy update**: Some alert message.\n\nThe rest of this answer may be outdated.",
                ),
                chunks_with_scores=[],
                subsections=subsections,
            )

    query_response, _metadata = await run_query(MockChatEngine(), "My question")
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
        query_response, _metadata = await run_query(MockChatEngine(), "My question")
        assert any(
            text == "LLM generated a citation for a reference (citation-44) that doesn't exist."
            for text in caplog.messages
        )

    assert query_response.response_text == "Response from LLM (citation-1)"
    assert len(query_response.citations) == 1
    assert query_response.citations[0].citation_id == "citation-1"


def test_get_chat_engine():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        literalai_user_id="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("ca-edd-web", retrieval_k=6),
        allowed_engines=["ca-edd-web"],
    )
    engine = get_chat_engine(session)
    assert engine.retrieval_k == 6


def test_get_chat_engine__unknown():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        literalai_user_id="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("engine_y"),
        allowed_engines=["ca-edd-web"],
    )
    with pytest.raises(HTTPException, match="Unknown engine: engine_y"):
        get_chat_engine(session)


def test_get_chat_engine_not_allowed():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        literalai_user_id="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("bridges-eligibility-manual"),
        allowed_engines=["ca-edd-web"],
    )
    with pytest.raises(HTTPException, match="Unknown engine: bridges-eligibility-manual"):
        get_chat_engine(session)


def test_post_feedback_success(client):
    response = client.post(
        "/api/feedback",
        json={
            "session_id": "Session2",
            "user_id": "user2",
            "is_positive": "true",
            "response_id": "response_id0",
            "comment": "great answer",
        },
    )

    assert response.status_code == 200


def test_post_feedback_fail(monkeypatch, client):
    try:
        client.post(
            "/api/feedback",
            json={
                "session_id": "Session2",
                "user_id": "user2",
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

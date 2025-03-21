import logging
import pytest

from contextlib import contextmanager
from typing import Optional
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from literalai import Score
from literalai.observability.step import ScoreType

from src import chat_api
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
    monkeypatch.setattr(chat_api, "literalai", lambda: MockLiteralAI())
    logger.info("Mocked literalai")


@pytest.fixture
def client(mock_lai, db_session):  # mock LiteralAI when testing API
    return TestClient(router)


@pytest.fixture
def async_client(mock_lai, db_session):  # mock LiteralAI when testing API
    return AsyncClient(transport=ASGITransport(app=router), base_url="http://test")


def test_api_engines(client):
    response = client.get("/api/engines?user_id=TestUser")
    assert response.status_code == 200
    assert response.json() == ["imagine-la"]


import asyncio
import concurrent.futures
import threading
import time

from asyncer import asyncify

logger = logging.getLogger(__name__)

# from unittest.mock import AsyncMock


def print_tasks(sleep=0):
    print("Sleeping")
    time.sleep(sleep)
    print("Awake")
    all_tasks = asyncio.all_tasks()
    # print("All tasks:", len(all_tasks))
    pending_tasks = [task for task in all_tasks if not task.done()]
    if True or len(pending_tasks) > 1:
        print("== Pending tasks:", len(pending_tasks))
        for i, task in enumerate(pending_tasks):
            print("-- Pending task", i, task.get_loop())
            print("  Coro: ", task.get_coro())
            # task.print_stack()
        # time.sleep(20)


@pytest.mark.asyncio
async def test_contextvar_dbsession(async_client, monkeypatch):
    event = threading.Event()

    async def wait_until_tested(db_session):
        # print("--")
        # logger.info("waiting: %r", db_session)
        event.wait()
        logger.info("waiting done")

    monkeypatch.setattr(chat_api, "wait_for_event", wait_until_tested)
    monkeypatch.setattr("src.chat_api.wait_for_event", wait_until_tested)

    async def checker_coroutine():
        logger.info("checker_coroutine waiting for 5 seconds")
        # await asyncio.sleep(5)
        time.sleep(3)
        logger.info("event.set()")
        event.set()

    async with async_client:
    # async with AsyncClient(transport=ASGITransport(app=router), base_url="http://test") as async_client1:
        call1 = async_client.get("/api/engines?user_id=TestUser1")
        call2 = async_client.get("/api/engines?user_id=TestUser2")
        checker = checker_coroutine()

        tasks = [asyncio.create_task(call) for call in [call1, call2, checker]]
        # asyncio.create_task(asyncify(print_tasks)(8))

        results = await asyncio.gather(*tasks)
        logger.info(results)

    assert "Forced" is False
    # assert response.status_code == 200

    # async with AsyncClient(transport=ASGITransport(app=router), base_url="http://test") as client:
    #     results = await asyncio.gather(
    #         client.get("/api/engines?user_id=TestUserA"),
    #         client.get("/api/engines?user_id=TestUserB"),
    #         # make_request(client, "/api/engines?user_id=TestUserA"),
    #         # make_request(client, "/api/engines?user_id=TestUserB"),
    #     )
    #     print(f"Request results: {results}")


@pytest.mark.asyncio
async def Atest_contextvar_db_oldclient(client, monkeypatch):
    event = threading.Event()

    async def wait_until_tested(db_session):
        logger.info("waiting: %r", db_session)
        event.wait()
        logger.info("waiting done")

    monkeypatch.setattr(chat_api, "wait_for_event", wait_until_tested)

    async def checker_coroutine():
        logger.info("asyncio waiting for 5 seconds")
        # await asyncio.sleep(5)
        time.sleep(3)
        logger.info("event.set()")
        event.set()

    # ensure that the TestClient and the application share the same event loop
    # with client:
    call1 = asyncify(lambda: client.get("/api/engines?user_id=TestUser1"))
    call2 = asyncify(lambda: client.get("/api/engines?user_id=TestUser2"))
    checker = checker_coroutine  # asyncify(check_vars)

    tasks = [asyncio.create_task(call()) for call in [call1, call2, checker]]
    results = await asyncio.gather(*tasks)
    logger.info(results)

    assert "Forced" is False
    # assert response.status_code == 200
    # assert response.json() == ["imagine-la"]


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

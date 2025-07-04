import asyncio
import logging

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from chainlit import data as cl_data
from src import chat_api
from src.chat_api import (
    ChatEngineSettings,
    ChatSession,
    QueryResponse,
    app_config,
    get_chat_engine,
    router,
    run_query,
)
from src.chat_engine import ImagineLA_MessageAttributes, OnMessageResult
from src.citations import CitationFactory, split_into_subsections
from src.db.models.conversation import Feedback, Step, Thread, User
from src.generate import MessageAttributes
from tests.src.db.models.factories import ChunkFactory, UserSessionFactory
from tests.src.test_chainlit_data import clear_data_layer_data


@pytest.fixture
def no_literalai_data_layer(monkeypatch):
    """
    Disables the LiteralAI data layer by clearing the API key environment variable
    and resetting the `literal_api_key_for_api` attribute in the app configuration.
    This prevents unintentional creation of the data layer during tests.
    """
    monkeypatch.setenv("LITERAL_API_KEY", "")
    monkeypatch.setattr(app_config, "literal_api_key_for_api", "")


@pytest.fixture
def async_client(no_literalai_data_layer, db_session, app_config):
    """
    The typical FastAPI TestClient creates its own event loop to handle requests,
    which led to issues when testing code that relies on asynchronous operations
    or resources tied to an event loop (i.e., ContextVars).
    To address errors like "RuntimeError: Task attached to a different loop",
    make tests asynchronous and directly use httpx.AsyncClient to work within the same event loop context.
    """
    reset_cl_data_layer()
    clear_data_layer_data(db_session)
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
    This only affects tests, where the router functions are called by the FastAPI's TestClient, as opposed to sending HTTP requests.

    TLDR: chat_api uses chainlit_data_layer, which uses asyncpg, which is tied to the event loop.
    Since tests can run in different event loops, we need to reset the chainlit_data_layer between tests.

    Alternative 1: Create a new FastAPI router for each test but router is referenced in many places
        (including API endpoints setup) so some references may point to the original router.
    Alternative 2: Use one event loop for all tests -- https://github.com/pytest-dev/pytest-asyncio/issues/924#issuecomment-2328433273.
    Alternative 3: Create a asyncio.new_event_loop(), asyncio.set_event_loop(new_loop),
        new_loop.run_until_complete(_cause_asyncpg_create_pool()), and new_loop.run_until_complete(_my_test())
    """
    cl_data._data_layer = None
    cl_data._data_layer_initialized = False


@pytest.mark.asyncio
async def test_api_engines(async_client, db_session):
    response = await async_client.get("/api/engines?user_id=TestUser")
    assert response.status_code == 200
    assert response.json() == ["imagine-la"]

    # Check persistence to DB
    users = db_session.query(User).all()
    assert len(users) == 1
    assert users[0].identifier == "TestUser"

    threads = db_session.query(Thread).all()
    assert len(threads) == 1
    assert threads[0].user_id == users[0].id

    steps = db_session.query(Step).order_by(Step.created_at).all()
    assert len(steps) == 2
    for step in steps:
        assert step.thread_id == threads[0].id
        assert step.is_error is False
    request_step = next(step for step in steps if step.type == "user_message")
    response_step = next(step for step in steps if step.type == "system_message")
    assert response_step.parent_id == request_step.id
    assert request_step.output == "List chat engines"
    assert response_step.output == "['imagine-la']"

    assert db_session.query(Feedback).count() == 0


@pytest.mark.asyncio
async def test_api_engines__dbsession_contextvar(async_client, monkeypatch, db_session, app_config):
    event = asyncio.Event()
    db_sessions = []
    orig_init_chat_session = chat_api._init_chat_session

    async def wait_for_all_requests(_self, *_args):
        db_session = chat_api.dbsession.get()
        db_sessions.append(db_session)
        if len(db_sessions) < 2:
            # Wait to allow the event loop to run other tasks
            await event.wait()
        # At this point, both requests should have been started and have their own DB session
        event.set()
        # Call original function
        return await orig_init_chat_session(_self, *_args)

    monkeypatch.setattr(chat_api, "_init_chat_session", wait_for_all_requests)

    async with async_client:
        call1 = async_client.get("/api/engines?user_id=TestUser1")
        call2 = async_client.get("/api/engines?user_id=TestUser2")

        tasks = [asyncio.create_task(call) for call in [call1, call2]]
        results = await asyncio.gather(*tasks)
        assert [r.status_code for r in results if r] == [200, 200]

    # chat_api.dbsession.get() should be distinct for each thread
    assert len(set(db_sessions)) == 2

    # Ensure all other asyncio tasks are done
    pending_tasks = [task for task in asyncio.all_tasks() if not task.done()]
    assert len(pending_tasks) == 1

    # Check persistence to DB
    assert set(db_session.execute(select(User.identifier)).scalars().all()) == set(
        ["TestUser1", "TestUser2"]
    )
    assert db_session.query(Thread).count() == 2
    assert db_session.query(Step).count() == 4
    assert db_session.query(Feedback).count() == 0


async def mock_run_query(engine, question, chat_history):
    return (
        QueryResponse(
            response_text=f"Response from LLM: {chat_history}",
            citations=[],
        ),
        {},
    )


@pytest.mark.asyncio
async def test_api_query(async_client, monkeypatch, db_session):
    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)
    response = await async_client.post(
        "/api/query",
        json={
            "user_id": "user9",
            "session_id": "Session0",
            "agency_id": "my_agency",
            "new_session": True,
            "message": "Hello",
        },
    )
    assert response.status_code == 200
    assert response.json()["response_text"] == "Response from LLM: []"

    user = db_session.query(User).first()
    assert user.identifier == "user9"
    assert user.metadata_col == {"agency_id": "my_agency"}

    # Posting again with new_session=True and the same session_id should fail
    with pytest.raises(
        HTTPException, match="Cannot start a new session 'Session0' that already exists"
    ) as e_info:
        await async_client.post(
            "/api/query",
            json={
                "user_id": "user9",
                "session_id": "Session0",
                "new_session": True,
                "message": "Hello again should fail",
            },
        )
    assert e_info.value.status_code == 409

    # Test chat history
    response = await async_client.post(
        "/api/query",
        json={
            "user_id": "user9",
            "session_id": "Session0",
            "agency_id": "my_updated_agency",
            "beneficiary_id": "my_beneficiary",
            "new_session": False,
            "message": "Hello again",
        },
    )
    assert response.status_code == 200
    assert (
        response.json()["response_text"]
        == "Response from LLM: [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Response from LLM: []'}]"
    )

    # Reset to force re-fetching from DB
    db_session.reset()
    # Check persistence to DB
    users = db_session.query(User).all()
    assert len(users) == 1
    assert users[0].identifier == "user9"
    assert users[0].metadata_col == {
        "agency_id": "my_updated_agency",
        "beneficiary_id": "my_beneficiary",
    }

    threads = db_session.query(Thread).all()
    assert len(threads) == 1
    assert threads[0].user_id == users[0].id

    steps = db_session.query(Step).order_by(Step.created_at).all()
    assert len(steps) == 4
    for step in steps:
        assert step.thread_id == threads[0].id
        assert step.is_error is False

    request_steps = [step for step in steps if step.type == "user_message"]
    response_steps = [step for step in steps if step.type == "assistant_message"]
    assert len(request_steps) == 2
    assert len(response_steps) == 2
    assert set(step.parent_id for step in response_steps) == set(step.id for step in request_steps)
    for request_step in request_steps:
        assert request_step.name == "user9"
    assert request_steps[0].output == "Hello"
    assert response_steps[0].output == "Response from LLM: []"
    assert request_steps[1].output == "Hello again"
    assert response_steps[1].output == response.json()["response_text"]

    assert db_session.query(Feedback).count() == 0


"""
@pytest.mark.asyncio
async def test_api_query__empty_user_id(async_client):
    with pytest.raises(RequestValidationError) as e_info:
        await async_client.post(
            "/api/query",
            json={
                "user_id": "",
                "session_id": "NewSession999",
                "new_session": False,
                "message": "Should fail",
            },
        )
    error = e_info.value.errors()[0]
    assert error["type"] == "string_too_short"
    assert error["msg"] == "String should have at least 1 character"
    assert error["loc"] == ("body", "user_id")
"""


@pytest.mark.asyncio
async def test_api_query__nonexistent_session_id(async_client, db_session):
    with pytest.raises(
        HTTPException, match="Existing session 'SessionForUser8' not found"
    ) as e_info:
        await async_client.post(
            "/api/query",
            json={
                "user_id": "user8",
                "session_id": "SessionForUser8",
                "new_session": False,
                "message": "Should fail",
            },
        )
    assert e_info.value.status_code == 409

    # Check persistence to DB
    assert db_session.query(User).count() == 0
    assert db_session.query(Thread).count() == 0
    assert db_session.query(Step).count() == 0
    assert db_session.query(Feedback).count() == 0


@pytest.mark.asyncio
async def test_api_query__user_session_mismatch(async_client, monkeypatch, db_session):
    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)
    await async_client.post(
        "/api/query",
        json={
            "user_id": "user9",
            "session_id": "SessionForUser9",
            "new_session": True,
            "message": "Question that starts new session",
        },
    )
    with pytest.raises(
        HTTPException, match="Session 'SessionForUser9' is not associated with user 'user10'"
    ) as e_info:
        await async_client.post(
            "/api/query",
            json={
                "user_id": "user10",
                "session_id": "SessionForUser9",
                "new_session": False,
                "message": "Should fail",
            },
        )
    assert e_info.value.status_code == 409

    # Check persistence to DB
    assert db_session.execute(select(User.identifier)).scalars().all() == ["user9"]
    assert db_session.query(Thread).count() == 1
    assert db_session.query(Step).count() == 2
    assert db_session.query(Feedback).count() == 0


@pytest.mark.asyncio
async def test_api_query__bad_request(async_client, db_session):
    with pytest.raises(RequestValidationError) as e_info:
        await async_client.post(
            "/api/query",
            json={"user_id": "user7", "session_id": "Session0", "new_session": True},
        )
    error = e_info.value.errors()[0]
    assert error["type"] == "missing"
    assert error["msg"] == "Field required"
    assert error["loc"] == ("body", "message")

    # Check persistence to DB
    assert db_session.query(User).count() == 0
    assert db_session.query(Thread).count() == 0
    assert db_session.query(Step).count() == 0
    assert db_session.query(Feedback).count() == 0


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
                MessageAttributes(needs_context=True, users_language="en", translated_message=""),
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
                    users_language="en",
                    translated_message="",
                    benefit_program="CalFresh",
                    canned_response="",
                    alert_message="Some alert message.",
                ),
                chunks_with_scores=[],
                subsections=subsections,
            )

    query_response, _metadata = await run_query(MockChatEngine(), "My question")
    assert query_response.alert_message == "Some alert message."
    assert (
        query_response.response_text
        == f"{query_response.alert_message}\n\nResponse from LLM (citation-1) (citation-2)"
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
                MessageAttributes(needs_context=True, users_language="en", translated_message=""),
                chunks_with_scores=[],
                subsections=subsections,
            )

    with caplog.at_level(logging.WARNING):
        query_response, _metadata = await run_query(MockChatEngine(), "My question")
        assert "Removing unknown 'citation-44'" in caplog.messages

    assert query_response.response_text == "Response from LLM (citation-1)"
    assert len(query_response.citations) == 1
    assert query_response.citations[0].citation_id == "citation-1"


def test_get_chat_engine():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        is_new=True,
        user_uuid="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("ca-edd-web", retrieval_k=6),
        allowed_engines=["ca-edd-web"],
    )
    engine = get_chat_engine(session)
    assert engine.retrieval_k == 6


def test_get_chat_engine__unknown():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        is_new=True,
        user_uuid="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("engine_y"),
        allowed_engines=["ca-edd-web"],
    )
    with pytest.raises(HTTPException, match="Unknown engine: engine_y"):
        get_chat_engine(session)


def test_get_chat_engine_not_allowed():
    session = ChatSession(
        user_session=UserSessionFactory.build(),
        is_new=True,
        user_uuid="some_literalai_user_id",
        chat_engine_settings=ChatEngineSettings("bridges-eligibility-manual"),
        allowed_engines=["ca-edd-web"],
    )
    with pytest.raises(HTTPException, match="Unknown engine: bridges-eligibility-manual"):
        get_chat_engine(session)


@pytest.mark.asyncio
async def test_api_post_feedback_success(async_client, monkeypatch, db_session):
    monkeypatch.setattr("src.chat_api.run_query", mock_run_query)
    response = await async_client.post(
        "/api/query",
        json={
            "user_id": "user11",
            "session_id": "Session_feedback",
            "new_session": True,
            "message": "Feedback test",
        },
    )
    assert response.status_code == 200
    step_id = response.json()["response_id"]
    assert step_id

    response = await async_client.post(
        "/api/feedback",
        json={
            "session_id": "Session_feedback",
            "user_id": "user11",
            "is_positive": "true",
            "response_id": step_id,
            "comment": "great answer",
        },
    )
    assert response.status_code == 200

    # Check feedback in DB
    assert db_session.execute(select(User.identifier)).scalars().all() == ["user11"]
    assert db_session.query(Thread).count() == 1
    assert db_session.query(Step).count() == 2
    response_step = db_session.query(Step).where(Step.id == step_id).first()
    assert response_step.type == "assistant_message"

    feedback_record = db_session.query(Feedback).where(Feedback.step_id == step_id).first()
    assert feedback_record.comment == "great answer"
    assert feedback_record.value == 1


@pytest.mark.asyncio
async def test_api_post_feedback_fail(async_client, db_session):
    with pytest.raises(RequestValidationError) as e_info:
        await async_client.post(
            "/api/feedback",
            json={
                "session_id": "Session_feedback_no_response_id",
                "user_id": "user2",
                "is_positive": "true",
                "comment": "great answer",
            },
        )
    error = e_info.value.errors()[0]
    assert error["type"] == "missing"
    assert error["msg"] == "Field required"
    assert error["loc"] == ("body", "response_id")

    # Check persistence to DB
    assert db_session.query(User).count() == 0
    assert db_session.query(Thread).count() == 0
    assert db_session.query(Step).count() == 0
    assert db_session.query(Feedback).count() == 0


# Add fixture to reset SSE AppStatus in tests
@pytest.fixture(autouse=True)
def reset_sse_starlette_appstatus_event():
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    # Fixture test from https://github.com/sysid/sse-starlette/issues/59#issuecomment-1961678665
    # See more here: https://github.com/sysid/sse-starlette/tree/main?tab=readme-ov-file#using-pytest-to-test-sse-endpoints


# Add tests for query_stream SSE endpoint
@pytest.mark.asyncio
async def test_query_stream_basic(async_client, monkeypatch, db_session):
    # Mock engine to yield two chunks without alert
    class MockEngine:
        async def on_message_streaming(self, question, chat_history):
            async def gen():
                yield "hello "
                yield "world"

            attributes = MessageAttributes(
                needs_context=False, users_language="en", translated_message=""
            )
            return gen(), attributes, []

    monkeypatch.setattr(chat_api, "get_chat_engine", lambda session: MockEngine())

    async def mock_run_query(engine, question, chat_history, streaming=True):
        return QueryResponse(response_text="final", alert_message=None, citations=[]), {}

    monkeypatch.setattr(chat_api, "run_query", mock_run_query)

    # Initialize streaming query
    init_response = await async_client.post(
        "/api/query_init",
        json={"user_id": "user1", "session_id": "session1", "new_session": True, "message": "Hi"},
    )
    assert init_response.status_code == 200
    message_id = init_response.json()["message_id"]

    # Stream SSE events
    url = f"/api/query_stream?id={message_id}&user_id=user1&session_id=session1"
    async with async_client.stream("GET", url) as response:
        assert response.status_code == 200
        events = []
        async for line in response.aiter_lines():
            if line.strip():
                events.append(line)

    # Validate streamed events
    assert "event: chunk" in events
    assert "data: hello " in events
    assert "data: world" in events
    assert "event: done" in events
    assert any("final" in line for line in events), f"Events: {events}"


@pytest.mark.asyncio
async def test_query_stream_with_alert(async_client, monkeypatch, db_session):
    # Mock engine to yield an alert before chunks
    class MockEngine:
        async def on_message_streaming(self, question, chat_history):
            async def gen():
                yield "data1"

            # Provide an attributes object with alert_message
            attributes = ImagineLA_MessageAttributes(
                needs_context=False,
                users_language="en",
                translated_message="",
                benefit_program="",
                canned_response="",
                alert_message="ALERT!",
            )
            return gen(), attributes, []

    monkeypatch.setattr(chat_api, "get_chat_engine", lambda session: MockEngine())

    async def mock_run_query(engine, question, chat_history, streaming=True):
        return QueryResponse(response_text="done", alert_message="ALERT!", citations=[]), {}

    monkeypatch.setattr(chat_api, "run_query", mock_run_query)

    # Initialize streaming query
    init_response = await async_client.post(
        "/api/query_init",
        json={
            "user_id": "user2",
            "session_id": "session2",
            "new_session": True,
            "message": "Hello",
        },
    )
    assert init_response.status_code == 200
    message_id = init_response.json()["message_id"]

    # Stream SSE events
    url = f"/api/query_stream?id={message_id}&user_id=user2&session_id=session2"
    async with async_client.stream("GET", url) as response:
        events = []
        async for line in response.aiter_lines():
            if line.strip():
                events.append(line)

    # Validate alert and chunk events
    assert "event: alert" in events
    assert "data: ALERT!" in events
    assert "event: chunk" in events
    assert "data: data1" in events
    assert "event: done" in events

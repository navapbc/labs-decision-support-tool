import datetime
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

import chainlit as cl
from chainlit.context import init_http_context
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from src import chainlit_data
from src.chainlit_data import ChainlitPolyDataLayer
from src.db.models.conversation import Element, Feedback, Step, Thread, User


def clear_data_layer_data(db_session):
    for table in [Element, Feedback, Step, Thread, User]:
        db_session.execute(delete(table))
    db_session.commit()


def init_chainlit_context():
    # https://github.com/Chainlit/chainlit/issues/1450#issuecomment-2441715453
    # Set up Chainlit context to enable calling methods like create_step()
    init_http_context()


@pytest.mark.asyncio
async def test_1_data_layer(db_session, monkeypatch):
    clear_data_layer_data(db_session)

    monkeypatch.setenv("LITERAL_API_KEY", "")
    data_layer = ChainlitPolyDataLayer()

    assert len(data_layer.data_layers) == 1
    assert isinstance(data_layer.data_layers[0], ChainlitDataLayer)

    assert await data_layer.get_user("test_user") is None
    user = cl.User(identifier="test_user", metadata={"test": True})
    assert (await data_layer.create_user(user)).identifier == "test_user"
    stored_user = await data_layer.get_user("test_user")
    assert stored_user.metadata == {"test": True}

    pagination = cl.types.Pagination(first=10)  # Get first 10 threads
    filters = cl.types.ThreadFilter(userId=stored_user.id)  # LiteralDataLayer requires userId
    paginated_resp = await data_layer.list_threads(pagination, filters)
    assert len(paginated_resp.data) == 0

    init_chainlit_context()

    thread_id = str(uuid.uuid4())
    step_dict = {
        "name": user.identifier,
        "type": "user_message",
        "id": str(uuid.uuid4()),
        "threadId": thread_id,
        "metadata": {"test_step": True},
        "start_time": datetime.datetime.now(),
        "end_time": datetime.datetime.now(),
        "output": "Tell me a joke",
    }

    # create_step() will create a thread if it doesn't exist
    await data_layer.create_step(step_dict)

    # Update thread attributes
    # update_thread() could be called before create_step()
    await data_layer.update_thread(thread_id, name="test thread", user_id=stored_user.id)
    paginated_resp = await data_layer.list_threads(pagination, filters)
    assert len(paginated_resp.data) == 1
    assert paginated_resp.data[0]["id"] == thread_id
    assert paginated_resp.data[0]["name"] == "test thread"
    assert paginated_resp.data[0]["userId"] == stored_user.id

    thread_dict = await data_layer.get_thread(thread_id)
    assert thread_dict["name"] == "test thread"
    assert thread_dict["userId"] == stored_user.id
    assert thread_dict["userIdentifier"] == user.identifier

    assert len(thread_dict["steps"]) == 1
    thread_step = thread_dict["steps"][0]
    assert thread_step["id"] == step_dict["id"]
    assert thread_step["name"] == user.identifier
    assert thread_step["type"] == "user_message"
    assert thread_step["metadata"] == {"test_step": True}
    assert thread_step["output"] == "Tell me a joke"

    author = await data_layer.get_thread_author(thread_id)
    assert author == user.identifier

    feedback = cl.types.Feedback(
        forId=thread_step["id"],
        value=0,
        comment="test comment",
    )
    feedback_id = await data_layer.upsert_feedback(feedback)

    # Add another feedback
    feedback = cl.types.Feedback(
        forId=thread_step["id"],
        value=0,
        comment="test comment 2",
    )
    feedback2_id = await data_layer.upsert_feedback(feedback)
    feedback_count = (
        db_session.query(Feedback).filter(Feedback.step_id == thread_step["id"]).count()
    )
    assert feedback_count == 2
    await data_layer.delete_feedback(feedback2_id)
    feedback_count = (
        db_session.query(Feedback).filter(Feedback.step_id == thread_step["id"]).count()
    )
    assert feedback_count == 1

    step_dict["isError"] = True
    await data_layer.update_step(step_dict)

    thread_dict = await data_layer.get_thread(thread_id)
    thread_step = thread_dict["steps"][0]
    assert thread_step["isError"] is True

    # Doesn't work; "feedback" is not present
    # feedback_dict = thread_step["feedback"]
    # So query DB directly
    feedback_record = db_session.query(Feedback).filter(Feedback.id == feedback_id).scalar()
    assert str(feedback_record.step_id) == thread_step["id"]
    assert feedback_record.comment == "test comment"

    await data_layer.delete_step(thread_step["id"])
    # Deleting the step deletes the feedback
    feedback_record = db_session.query(Feedback).filter(Feedback.id == feedback_id).scalar()
    assert feedback_record is None
    thread_dict = await data_layer.get_thread(thread_id)
    assert len(thread_dict["steps"]) == 0

    await data_layer.delete_thread(thread_id)
    thread_dict = await data_layer.get_thread(thread_id)
    assert thread_dict is None


@pytest.fixture
def literalai_data_layer(monkeypatch):
    mock_literalai_dl = AsyncMock()
    mock_literalai_dl.get_user.side_effect = ValueError("mock error")
    monkeypatch.setattr(chainlit_data, "get_literal_data_layer", lambda _key: mock_literalai_dl)


@pytest.mark.asyncio
async def test_exception_in_secondary_layer(db_session, monkeypatch, literalai_data_layer, caplog):
    clear_data_layer_data(db_session)

    monkeypatch.setenv("LITERAL_API_KEY", "dummy_key")
    data_layer = ChainlitPolyDataLayer()

    assert len(data_layer.data_layers) == 2

    assert isinstance(data_layer.data_layers[0], ChainlitDataLayer)
    assert isinstance(data_layer.data_layers[1], AsyncMock)

    with caplog.at_level(logging.WARNING):
        # Expect no raised errork, only a warning message
        assert await data_layer.get_user("test_user") is None
        assert "Error in non-primary data layer 1: mock error" in caplog.messages


@pytest.mark.asyncio
async def test_exception_in_primary_layer(db_session, monkeypatch, caplog):
    clear_data_layer_data(db_session)

    monkeypatch.setenv("LITERAL_API_KEY", "dummy_key")
    monkeypatch.setattr(chainlit_data, "get_literal_data_layer", lambda _key: AsyncMock())

    data_layer = ChainlitPolyDataLayer()

    assert len(data_layer.data_layers) == 2

    assert isinstance(data_layer.data_layers[0], ChainlitDataLayer)
    assert isinstance(data_layer.data_layers[1], AsyncMock)

    async def mock_get_user(_key):
        raise ZeroDivisionError("mock error")

    monkeypatch.setattr(data_layer.data_layers[0], "get_user", mock_get_user)

    with caplog.at_level(logging.WARNING):
        try:
            # Expect error to be raised
            await data_layer.get_user("test_user")
            raise AssertionError("Expected ZeroDivisionError")
        except ZeroDivisionError:
            pass
        assert "Error in primary data layer: mock error" in caplog.messages

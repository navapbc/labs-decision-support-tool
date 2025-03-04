from sqlalchemy import delete, select

import src.adapters.db as db
from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Chunk, Document
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import (
    ChatMessageFactory,
    ChunkFactory,
    DocumentFactory,
    UserSessionFactory,
)


def test_document_factory(enable_factory_create, db_session: db.Session):
    # Delete Documents created by other tests
    db_session.execute(delete(Document))

    document = DocumentFactory.create()

    db_record = db_session.execute(select(Document)).scalar_one()
    assert db_record.id == document.id
    assert db_record.content == document.content
    assert db_record.name == document.name
    assert db_record.dataset == document.dataset
    assert db_record.program == document.program
    assert db_record.region == document.region


def test_chunk_factory(enable_factory_create, db_session: db.Session):
    # Delete Documents and Chunks (by cascade) created by other tests
    db_session.execute(delete(Document))

    chunk = ChunkFactory.create()

    document_db_record = db_session.execute(select(Document)).scalar_one()
    assert document_db_record.id == chunk.document_id

    chunk_db_record = db_session.execute(select(Chunk)).scalar_one()
    assert chunk_db_record.id == chunk.id
    assert chunk_db_record.content == chunk.content
    assert chunk_db_record.tokens == len(
        MockSentenceTransformer().tokenizer.tokenize(chunk.content)
    )
    assert chunk_db_record.mpnet_embedding == MockSentenceTransformer().encode(chunk.content)


def test_user_session_factory(enable_factory_create, db_session: db.Session):
    # Delete UserSession created by other tests
    db_session.execute(delete(UserSession))

    user_session = UserSessionFactory.create()
    user_session_record = db_session.execute(select(UserSession)).scalar_one()
    assert user_session_record.session_id == user_session.session_id
    assert user_session_record.user_id == user_session.user_id
    assert user_session_record.chat_engine_id == user_session.chat_engine_id
    assert user_session_record.lai_thread_id == user_session.lai_thread_id
    assert user_session_record.created_at == user_session.created_at
    assert user_session_record.updated_at == user_session.updated_at
    assert user_session_record.chat_messages == []


def test_chat_message_factory(db_session: db.Session, enable_factory_create):
    # Delete UserSession and ChatMessage records created by other tests
    db_session.execute(delete(ChatMessage))
    db_session.execute(delete(UserSession))

    # Create some messages for the same user session
    user_session = UserSessionFactory.create()
    ChatMessageFactory.create_batch(4, session=user_session)
    assert db_session.query(ChatMessage).count() == 4
    assert db_session.query(UserSession).count() == 1

    for msg in user_session.chat_messages:
        assert msg.session_id == user_session.session_id
        assert msg.session == user_session

    # Create messages with a specific session_id to test
    user_session2 = UserSessionFactory.create()
    msgs: list[ChatMessage] = ChatMessageFactory.create_batch(3, session=user_session2)
    # Prepend the message content with the index so the ordering is obvious
    for i, msg in enumerate(msgs):
        msg.content = f"Message {i}: {msg.content}"

    # Create some more messages
    ChatMessageFactory.create_batch(5)

    assert db_session.query(ChatMessage).count() == 12

    all_msgs = db_session.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == user_session2.session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    assert len(all_msgs) == 3
    for i, msg in enumerate(all_msgs):
        assert msg.content.startswith(f"Message {i}: ")

    for i, msg in enumerate(user_session2.chat_messages):
        assert msg.content.startswith(f"Message {i}: ")

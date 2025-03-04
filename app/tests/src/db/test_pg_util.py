import logging
import os
import tempfile

from sqlalchemy import delete, select

from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Chunk, Document
from src.db.pg_util import backup_db, restore_db
from tests.src.db.models.factories import (
    ChatMessageFactory,
    ChunkFactory,
    UserSessionFactory,
)


def test_backup_and_restore_db(enable_factory_create, db_session, caplog):
    db_session.execute(delete(Document))
    db_session.execute(delete(UserSession))
    db_session.execute(delete(ChatMessage))

    ChunkFactory.create()
    document_db_record = db_session.execute(select(Document)).scalar_one()
    ChunkFactory.create_batch(4, document=document_db_record)

    user_session = UserSessionFactory.create()
    ChatMessageFactory.create_batch(4, session=user_session)

    doc_results = db_session.query(Document.id, Document.content).all()
    chunk_results = db_session.query(Chunk.id, Chunk.content).all()
    session_results = db_session.query(UserSession.session_id, UserSession.chat_engine_id).all()
    message_results = db_session.query(ChatMessage.id, ChatMessage.content).all()

    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"
        backup_db()

        assert "Table 'document' has 1 rows" in caplog.messages
        assert "Table 'chunk' has 5 rows" in caplog.messages
        assert "Table 'user_session' has 1 rows" in caplog.messages
        assert "Table 'chat_message' has 4 rows" in caplog.messages
        assert f"Output written to '{tmpdirname}/db.dump'" in caplog.messages
        assert "Skipping S3 upload since running in local environment" in caplog.messages

        restore_db()
        assert "Clearing out tables" in caplog.messages
        assert "Stdout: TRUNCATE TABLE" in caplog.messages
        assert "Tables truncated" in caplog.messages

        # assert "Table 'document' has 0 rows" in caplog.messages
        # assert "Table 'chunk' has 0 rows" in caplog.messages
        # assert "Table 'user_session' has 0 rows" in caplog.messages
        # assert "Table 'chat_message' has 0 rows" in caplog.messages

        assert not any(msg.startswith("Stderr") for msg in caplog.messages)

    assert db_session.query(Document).count() == 1
    assert db_session.query(Chunk).count() == 5
    assert db_session.query(UserSession).count() == 1
    assert db_session.query(ChatMessage).count() == 4

    assert db_session.query(Document.id, Document.content).all() == doc_results
    assert db_session.query(Chunk.id, Chunk.content).all() == chunk_results
    assert (
        db_session.query(UserSession.session_id, UserSession.chat_engine_id).all()
        == session_results
    )
    assert db_session.query(ChatMessage.id, ChatMessage.content).all() == message_results

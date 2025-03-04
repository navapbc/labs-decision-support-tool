import logging
import os
import tempfile

from sqlalchemy import delete, select

from src.db import pg_util
from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Document
from tests.src.db.models.factories import ChatMessageFactory, ChunkFactory, UserSessionFactory


def test_backup_and_restore_db(enable_factory_create, db_session, caplog, monkeypatch):
    db_session.execute(delete(Document))
    db_session.execute(delete(UserSession))
    db_session.execute(delete(ChatMessage))

    ChunkFactory.create()
    document_db_record = db_session.execute(select(Document)).scalar_one()
    ChunkFactory.create_batch(4, document=document_db_record)

    user_session = UserSessionFactory.create()
    ChatMessageFactory.create_batch(4, session=user_session)

    def _mock_run_command(_command, _stdout_file=None) -> bool:
        return True

    monkeypatch.setattr(pg_util, "_run_command", _mock_run_command)

    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"
        pg_util.backup_db()

        assert "Table 'document' has 1 rows" in caplog.messages
        assert "Table 'chunk' has 5 rows" in caplog.messages
        assert "Table 'user_session' has 1 rows" in caplog.messages
        assert "Table 'chat_message' has 4 rows" in caplog.messages
        assert f"DB data dumped to '{tmpdirname}/db.dump'" in caplog.messages
        assert "Skipping S3 upload since running in local environment" in caplog.messages

        # Avoid sleep by explicitly setting TRUNCATE_TABLES
        os.environ["TRUNCATE_TABLES"] = "true"
        pg_util.restore_db()
        assert "Clearing out tables" in caplog.messages
        assert "Tables truncated" in caplog.messages

        assert not any(msg.startswith("Stderr") for msg in caplog.messages)

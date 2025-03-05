import logging
import os
import re
import tempfile

from sqlalchemy import delete, select

from src.db import pg_util
from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Document
from tests.src.db.models.factories import ChatMessageFactory, ChunkFactory, UserSessionFactory


def _prep_test(db_session, monkeypatch, run_command_return_value=True):
    db_session.execute(delete(Document))
    db_session.execute(delete(ChatMessage))
    db_session.execute(delete(UserSession))

    ChunkFactory.create()
    document_db_record = db_session.execute(select(Document)).scalar_one()
    ChunkFactory.create_batch(4, document=document_db_record)

    user_session = UserSessionFactory.create()
    ChatMessageFactory.create_batch(4, session=user_session)

    def _mock_run_command(_command, _stdout_file=None) -> bool:
        # Don't run any commands b/c they affect the real DB
        return run_command_return_value

    monkeypatch.setattr(pg_util, "_run_command", _mock_run_command)

    # For testing restore_db(), avoid sleep() by explicitly setting TRUNCATE_TABLES
    os.environ["TRUNCATE_TABLES"] = "true"


def test_backup_and_restore_db(enable_factory_create, db_session, caplog, monkeypatch):
    _prep_test(db_session, monkeypatch)

    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"
        pg_util.backup_db()

        assert "Table 'document' has 1 rows" in caplog.messages
        assert "Table 'chunk' has 5 rows" in caplog.messages
        assert "Table 'user_session' has 1 rows" in caplog.messages
        assert "Table 'chat_message' has 4 rows" in caplog.messages
        assert f"DB data dumped to '{tmpdirname}/db.dump'" in caplog.messages
        assert "Skipping S3 upload since running in local environment" in caplog.messages

        for msg in caplog.messages:
            print(msg)

        pg_util.restore_db()
        assert "Clearing out tables" in caplog.messages
        assert "Tables truncated" in caplog.messages
        assert f"DB data restored from {os.environ["PG_DUMP_FILE"]!r}" in caplog.messages


def test_backup_db_failure(enable_factory_create, db_session, caplog, monkeypatch):
    _prep_test(db_session, monkeypatch, run_command_return_value=False)

    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"
        pg_util.backup_db()

        assert f"Failed to dump DB data to '{tmpdirname}/db.dump'" in caplog.messages


def test_backup_db_for_dev(enable_factory_create, db_session, caplog, monkeypatch):
    os.environ["ENVIRONMENT"] = "dev"

    _prep_test(db_session, monkeypatch)

    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"
        pg_util.backup_db()

        assert any(
            re.match(
                f"DB dump uploaded to s3://decision-support-tool-app-dev/pg_dumps/{tmpdirname}/db-.*.dump",
                msg,
            )
            for msg in caplog.messages
        )


def test_restore_db_failure(enable_factory_create, db_session, caplog, monkeypatch):
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        os.environ["PG_DUMP_FILE"] = f"{tmpdirname}/db.dump"

        pg_util.restore_db()
        assert (
            f"File '{tmpdirname}/db.dump' not found; please set PG_DUMP_FILE to a valid file"
            in caplog.messages
        )

        assert "Tables truncated" not in caplog.messages
        assert f"DB data restored from {os.environ["PG_DUMP_FILE"]}" not in caplog.messages

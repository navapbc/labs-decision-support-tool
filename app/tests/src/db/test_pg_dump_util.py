import logging
import re
import tempfile

import pytest
from sqlalchemy import delete, select

from src.db import pg_dump_util
from src.db.models.conversation import ChatMessage, UserSession
from src.db.models.document import Document
from tests.src.db.models.factories import ChatMessageFactory, ChunkFactory, UserSessionFactory


@pytest.fixture
def populated_db(db_session):
    db_session.execute(delete(Document))
    db_session.execute(delete(ChatMessage))
    db_session.execute(delete(UserSession))

    ChunkFactory.create()
    document_db_record = db_session.execute(select(Document)).scalar_one()
    ChunkFactory.create_batch(4, document=document_db_record)

    user_session = UserSessionFactory.create()
    ChatMessageFactory.create_batch(4, session=user_session)


def test_backup_and_restore_db(enable_factory_create, populated_db, app_config, caplog):
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"
        pg_dump_util.backup_db(dumpfile, "local")

        assert "Table 'document' has 1 rows" in caplog.messages
        assert "Table 'chunk' has 5 rows" in caplog.messages
        assert "Table 'user_session' has 1 rows" in caplog.messages
        assert "Table 'chat_message' has 4 rows" in caplog.messages
        assert f"DB data dumped to '{tmpdirname}/db.dump'" in caplog.messages
        assert "Skipping S3 upload since running in local environment" in caplog.messages

        pg_dump_util.restore_db(dumpfile, False, 0)
        assert "Clearing out tables" in caplog.messages
        assert "Tables truncated" in caplog.messages
        assert f"DB data restored from {dumpfile!r}" in caplog.messages


def test_restore_db_without_truncating(caplog):
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"
        with open(dumpfile, "wb"):  # Create an empty file
            pass
        pg_dump_util.restore_db(dumpfile, True, 0)
        assert (
            "Skipping truncating tables; will attempt to append to existing data" in caplog.messages
        )


def test_backup_db__file_exists(caplog):
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"
        with open(dumpfile, "wb"):  # Create an empty file
            pass
        pg_dump_util.backup_db(dumpfile, "local")

        assert (
            f"File '{tmpdirname}/db.dump' already exists; delete or move it first or specify a different file using --dumpfile"
            in caplog.messages
        )
        assert f"DB data dumped to '{tmpdirname}/db.dump'" not in caplog.messages


def test_backup_db__dump_failure(caplog, monkeypatch):
    monkeypatch.setattr(pg_dump_util, "_pg_dump", lambda *args: False)
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"
        pg_dump_util.backup_db(dumpfile, "local")

        assert f"Failed to dump DB data to '{tmpdirname}/db.dump'" in caplog.messages


def test_backup_db__truncate_failure(caplog, monkeypatch):
    monkeypatch.setattr(pg_dump_util, "_truncate_db_tables", lambda *args: False)
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"
        with open(dumpfile, "wb"):
            pass
        pg_dump_util.restore_db(dumpfile, False, 0)

        assert "Failed to truncate tables" in caplog.messages


@pytest.fixture
def mock_s3_dev_bucket(mock_s3):
    bucket = mock_s3.Bucket("decision-support-tool-app-dev")
    bucket.create()
    yield bucket


def test_backup_db_for_dev(
    enable_factory_create, populated_db, app_config, caplog, mock_s3_dev_bucket
):
    with caplog.at_level(logging.INFO):
        dumpfile = "dev_db.dump"
        pg_dump_util.backup_db(dumpfile, "dev")

    assert any(
        re.match(
            "Writing DB dump to 's3://decision-support-tool-app-dev/pg_dumps/dev_db-.*.dump'",
            msg,
        )
        for msg in caplog.messages
    )


def test_restore_db_failure(caplog):
    with caplog.at_level(logging.INFO), tempfile.TemporaryDirectory() as tmpdirname:
        dumpfile = f"{tmpdirname}/db.dump"

        pg_dump_util.restore_db(dumpfile, False, 0)
        assert f"File '{tmpdirname}/db.dump' not found" in caplog.messages

        assert "Tables truncated" not in caplog.messages
        assert f"DB data restored from {dumpfile}" not in caplog.messages

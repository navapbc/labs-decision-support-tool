import logging
from unittest.mock import ANY, Mock

from sqlalchemy import delete, select

from src.db.models.document import Document
from src.util.ingest_utils import (
    _drop_existing_dataset,
    add_embeddings,
    process_and_ingest_sys_args,
    tokenize,
)
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


def test__drop_existing_dataset(db_session, enable_factory_create):
    db_session.execute(delete(Document))

    docs = DocumentFactory(dataset="1"), DocumentFactory(dataset="2")

    # This shouldn't do anything
    assert _drop_existing_dataset(db_session, "nonexistent dataset") is False
    assert len(db_session.execute(select(Document)).all()) == 2

    # After this, the only document left should be the second one
    assert _drop_existing_dataset(db_session, docs[0].dataset) is True
    assert db_session.execute(select(Document)).one()[0].dataset == docs[1].dataset


def test_process_and_ingest_sys_args_requires_four_args(caplog):
    logger = logging.getLogger(__name__)
    ingest = Mock()

    with caplog.at_level(logging.WARNING):
        process_and_ingest_sys_args(["ingest-policy-pdfs"], logger, ingest)
        assert "Expecting 4 arguments" in caplog.text
        assert not ingest.called

    with caplog.at_level(logging.WARNING):
        process_and_ingest_sys_args(
            ["ingest-policy-pdfs", "with", "too", "many", "args", "passed"], logger, ingest
        )
        assert "Expecting 4 arguments" in caplog.text
        assert not ingest.called


def test_process_and_ingest_sys_args_calls_ingest(caplog):
    logger = logging.getLogger(__name__)
    ingest = Mock()

    with caplog.at_level(logging.INFO):
        process_and_ingest_sys_args(
            [
                "ingest-policy-pdfs",
                "bridges-eligibility-manual",
                "SNAP",
                "Michigan",
                "/some/folder",
            ],
            logger,
            ingest,
        )
        assert "Finished processing" in caplog.text
        ingest.assert_called_with(
            ANY,
            "/some/folder",
            {
                "dataset": "bridges-eligibility-manual",
                "program": "SNAP",
                "region": "Michigan",
            },
        )


def test_process_and_ingest_sys_args_drops_existing_dataset(
    db_session, caplog, enable_factory_create
):
    db_session.execute(delete(Document))
    logger = logging.getLogger(__name__)
    ingest = Mock()

    DocumentFactory.create(dataset="other dataset")

    with caplog.at_level(logging.WARNING):
        process_and_ingest_sys_args(
            [
                "ingest-policy-pdfs",
                "bridges-eligibility-manual",
                "SNAP",
                "Michigan",
                "/some/folder",
            ],
            logger,
            ingest,
        )
        assert "Dropped existing dataset" not in caplog.text
        assert db_session.execute(select(Document).where(Document.dataset == "other dataset")).one()

    DocumentFactory.create(dataset="bridges-eligibility-manual")

    with caplog.at_level(logging.WARNING):
        process_and_ingest_sys_args(
            [
                "ingest-policy-pdfs",
                "bridges-eligibility-manual",
                "SNAP",
                "Michigan",
                "/some/folder",
            ],
            logger,
            ingest,
        )
        assert "Dropped existing dataset" in caplog.text
        assert (
            db_session.execute(
                select(Document).where(Document.dataset == "bridges-eligibility-manual")
            ).one_or_none()
            is None
        )
        assert db_session.execute(select(Document).where(Document.dataset == "other dataset")).one()


def test__add_embeddings(app_config):
    embedding_model = MockSentenceTransformer()
    chunks = ChunkFactory.build_batch(3, tokens=None, mpnet_embedding=None)
    add_embeddings(chunks)
    for chunk in chunks:
        assert chunk.tokens == len(tokenize(chunk.content))
        assert chunk.mpnet_embedding == embedding_model.encode(chunk.content)

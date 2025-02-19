import json
import logging
import os
import tempfile
from unittest.mock import Mock

import pytest
from smart_open import open
from sqlalchemy import delete, select

from src.db.models.document import Document
from src.util.ingest_utils import (
    IngestConfig,
    _drop_existing_dataset,
    add_embeddings,
    process_and_ingest_sys_args,
    save_json,
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


default_config = IngestConfig(
    "Benefits Information Hub",
    "mixed",
    "California",
    "https://benefitnavigator.web.app/contenthub/",
    "imagine_la_md",
)


def test_process_and_ingest_sys_args_requires_four_args(caplog):
    logger = logging.getLogger(__name__)
    ingest = Mock()

    with pytest.raises(SystemExit):
        with caplog.at_level(logging.WARNING):
            process_and_ingest_sys_args(["ingest-policy-pdfs"], logger, ingest, default_config)
            assert "the following arguments are required:" in caplog.text
            assert not ingest.called

    with pytest.raises(SystemExit):
        with caplog.at_level(logging.WARNING):
            process_and_ingest_sys_args(
                ["ingest-policy-pdfs", "with", "too", "many", "args", "passed"],
                logger,
                ingest,
                default_config,
            )
            assert "the following arguments are required:" in caplog.text
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
            default_config,
        )
        assert "Finished ingesting" in caplog.text

        call_args = ingest.call_args
        assert call_args[0][1] == "/some/folder"
        ingest_config = call_args[0][2]
        assert isinstance(ingest_config, IngestConfig)
        assert ingest_config.dataset_label == "bridges-eligibility-manual"
        assert ingest_config.benefit_program == "SNAP"
        assert ingest_config.benefit_region == "Michigan"
        assert call_args[1] == {"skip_db": False}


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
            default_config,
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
            default_config,
        )
        assert "Dropped existing dataset" in caplog.text
        assert (
            db_session.execute(
                select(Document).where(Document.dataset == "bridges-eligibility-manual")
            ).one_or_none()
            is None
        )
        assert db_session.execute(select(Document).where(Document.dataset == "other dataset")).one()


def test_process_and_ingest_sys_args_resume(db_session, caplog, enable_factory_create):
    db_session.execute(delete(Document))
    logger = logging.getLogger(__name__)
    ingest = Mock()
    with pytest.raises(NotImplementedError):
        process_and_ingest_sys_args(
            [
                "ingest-policy-pdfs",
                "bridges-eligibility-manual",
                "SNAP",
                "Michigan",
                "/some/folder",
                "--resume",
            ],
            logger,
            ingest,
            default_config,
        )

    # Use an unmocked function so that the resume parameter is detectable by process_and_ingest_sys_args()
    def ingest_with_resume(
        db_session, json_filepath, doc_attribs, skip_db=False, resume=False
    ) -> None:
        logger.info("Ingesting with resume: %r", resume)

    DocumentFactory.create(dataset="CA EDD")
    with caplog.at_level(logging.INFO):
        process_and_ingest_sys_args(
            [
                "ingest-edd-web",
                "CA EDD",
                "employment",
                "California",
                "/some/folder",
                "--resume",
            ],
            logger,
            ingest_with_resume,
            default_config,
        )
        assert "Enabled resuming from previous run" in caplog.text
        assert "Ingesting with resume: True" in caplog.text
        assert "Dropped existing dataset" not in caplog.text
        assert db_session.execute(select(Document).where(Document.dataset == "CA EDD")).one()


def test__add_embeddings(app_config):
    embedding_model = MockSentenceTransformer()
    chunks = ChunkFactory.build_batch(3, tokens=None, mpnet_embedding=None)
    add_embeddings(chunks)
    for chunk in chunks:
        assert chunk.tokens == len(tokenize(chunk.content))
        assert chunk.mpnet_embedding == embedding_model.encode(chunk.content)


def test__add_embeddings_with_texts_to_encode(app_config):
    embedding_model = MockSentenceTransformer()
    chunks = ChunkFactory.build_batch(3, tokens=None, mpnet_embedding=None)
    texts_to_encode = ["text1", "text2", "text3"]
    add_embeddings(chunks, texts_to_encode)
    for chunk, text in zip(chunks, texts_to_encode, strict=True):
        assert chunk.tokens == len(tokenize(text))
        assert chunk.mpnet_embedding == embedding_model.encode(text)


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__save_json(file_location, mock_s3_bucket_resource):
    chunks = ChunkFactory.build_batch(2)
    file_path = (
        "s3://test_bucket/test.pdf"
        if file_location == "s3"
        else os.path.join(tempfile.mkdtemp(), "test.pdf")
    )
    json_file = f"{file_path}.json"
    save_json(json_file, chunks)
    saved_json = json.loads(open(json_file, "r").read())
    assert saved_json == [
        {
            "id": str(chunks[0].id),
            "content": chunks[0].content,
            "document_id": str(chunks[0].document_id),
            "headings": chunks[0].headings if chunks[0].headings else [],
            "num_splits": chunks[0].num_splits,
            "split_index": chunks[0].split_index,
        },
        {
            "id": str(chunks[1].id),
            "content": chunks[1].content,
            "document_id": str(chunks[1].document_id),
            "headings": chunks[1].headings if chunks[1].headings else [],
            "num_splits": chunks[1].num_splits,
            "split_index": chunks[1].split_index,
        },
    ]

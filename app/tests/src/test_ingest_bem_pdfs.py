import json
import logging
import os
import tempfile

import pytest
from smart_open import open as smart_open
from sqlalchemy import delete, select

from src.db.models.document import Document
from src.ingest_bem_pdfs import _add_embeddings, _get_bem_title, _ingest_bem_pdfs, _save_json
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory
from tests.src.test_ingest_policy_pdfs import doc_attribs


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource):
    data = smart_open("/app/tests/src/util/707.pdf", "rb")
    mock_s3_bucket_resource.put_object(Body=data, Key="707.pdf")
    return "s3://test_bucket/"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__get_bem_title(file_location, policy_s3_file):
    file_path = (
        policy_s3_file + "707.pdf" if file_location == "s3" else "/app/tests/src/util/707.pdf"
    )
    with smart_open(file_path, "rb") as file:
        assert _get_bem_title(file, file_path) == "BEM 707: TIME AND ATTENDANCE REVIEWS"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_bem_pdfs(caplog, app_config, db_session, policy_s3_file, file_location):
    db_session.execute(delete(Document))

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            _ingest_bem_pdfs(db_session, "/app/tests/src/util/", doc_attribs)
        else:
            _ingest_bem_pdfs(db_session, policy_s3_file, doc_attribs)

        assert any(text.startswith("Processing file: ") for text in caplog.messages)
        document = db_session.execute(select(Document)).one()[0]
        assert document.dataset == "test_dataset"
        assert document.program == "test_benefit_program"
        assert document.region == "Michigan"

        assert document.name == "BEM 707: TIME AND ATTENDANCE REVIEWS"

        # TODO: Test Document.content
        # assert "Temporary Assistance to Needy Families" in document.content
        # assert "The Food Assistance Program" in document.content

        # TODO: Test: The document should be broken into two chunks, which
        # have different content and different embeddings
        # first_chunk, second_chunk = document.chunks
        # assert "Temporary Assistance to Needy Families" in first_chunk.content
        # assert "The Food Assistance Program" not in first_chunk.content
        # assert math.isclose(first_chunk.mpnet_embedding[0], -0.7016304, rel_tol=1e-5)

        # assert "Temporary Assistance to Needy Families" not in second_chunk.content
        # assert "The Food Assistance Program" in second_chunk.content
        # assert math.isclose(second_chunk.mpnet_embedding[0], -0.82242084, rel_tol=1e-3)

    # Clean up the temporary file
    if file_location == "local":
        os.remove("/app/tests/docs/100.pdf.json")


def test__add_embeddings(app_config):
    embedding_model = MockSentenceTransformer()
    chunks = ChunkFactory.build_batch(3, tokens=None, mpnet_embedding=None)
    _add_embeddings(chunks)
    for chunk in chunks:
        assert chunk.tokens == len(embedding_model.tokenizer.tokenize(chunk.content))
        assert chunk.mpnet_embedding == embedding_model.encode(chunk.content)


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__save_json(file_location, mock_s3_bucket_resource):
    chunks = ChunkFactory.build_batch(2)
    file_path = (
        "s3://test_bucket/test.pdf"
        if file_location == "s3"
        else os.path.join(tempfile.mkdtemp(), "test.pdf")
    )
    _save_json(file_path, chunks)
    saved_json = json.loads(smart_open(file_path + ".json", "r").read())
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

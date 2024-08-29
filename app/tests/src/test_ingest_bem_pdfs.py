import logging

import pytest
from smart_open import open as smart_open
from sqlalchemy import delete, select

from src.db.models.document import Document
from src.ingest_bem_pdfs import _get_bem_title, _ingest_bem_pdfs
from tests.src.test_ingest_policy_pdfs import doc_attribs


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource):
    data = smart_open("/app/tests/docs/100.pdf", "rb")
    mock_s3_bucket_resource.put_object(Body=data, Key="100.pdf")
    return "s3://test_bucket/"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__get_bem_title(file_location, policy_s3_file):
    file_path = policy_s3_file + "100.pdf" if file_location == "s3" else "/app/tests/docs/100.pdf"
    with smart_open(file_path, "rb") as file:
        assert _get_bem_title(file, file_path) == "BEM 100: INTRODUCTION"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_bem_pdfs(caplog, app_config, db_session, policy_s3_file, file_location):
    db_session.execute(delete(Document))

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            _ingest_bem_pdfs(db_session, "/app/tests/docs/", doc_attribs)
        else:
            _ingest_bem_pdfs(db_session, policy_s3_file, doc_attribs)

        assert any(text.startswith("Processing file: ") for text in caplog.messages)
        document = db_session.execute(select(Document)).one()[0]
        assert document.dataset == "test_dataset"
        assert document.program == "test_benefit_program"
        assert document.region == "Michigan"

        assert document.name == "BEM 100: INTRODUCTION"

        # TODO: Test Document.content
        assert "BEM 100" in document.content
        assert "The Food Assistance Program" in document.content

        # TODO: Test: The document should be broken into two chunks, which
        # have different content and different embeddings
        # first_chunk, second_chunk = document.chunks
        # assert "Temporary Assistance to Needy Families" in first_chunk.content
        # assert "The Food Assistance Program" not in first_chunk.content
        # assert math.isclose(first_chunk.mpnet_embedding[0], -0.7016304, rel_tol=1e-5)

        # assert "Temporary Assistance to Needy Families" not in second_chunk.content
        # assert "The Food Assistance Program" in second_chunk.content
        # assert math.isclose(second_chunk.mpnet_embedding[0], -0.82242084, rel_tol=1e-3)

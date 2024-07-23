import io
import logging
import tempfile
from unittest import mock

import pytest
from sqlalchemy import delete, select

from src.db.models.document import Document
from src.ingest_policy_pdfs import _ingest_policy_pdfs
from tests.mock.mock_sentence_transformer import MockSentenceTransformer


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource):
    mock_s3_bucket_resource.put_object(
        Body=io.BytesIO(b"%PDF-1.4\n%Fake PDF content for testing\n"), Key="policy.pdf"
    )
    return "s3://test_bucket/policy.pdf"


doc_attribs = {
    "dataset": "test_dataset",
    "program": "test_benefit_program",
    "region": "Michigan",
}


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_policy_pdfs(caplog, db_session, policy_s3_file, file_location):
    db_session.execute(delete(Document))
    mock_embedding = MockSentenceTransformer()

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            with tempfile.TemporaryDirectory() as tmpdirname:
                tempfile.NamedTemporaryFile(
                    prefix="policy", suffix=".pdf", dir=tmpdirname, delete=False
                )
                _ingest_policy_pdfs(db_session, mock_embedding, tmpdirname, doc_attribs)
        else:
            _ingest_policy_pdfs(db_session, mock_embedding, policy_s3_file, doc_attribs)

        assert any(text.startswith("Processing pdf file:") for text in caplog.messages)
        assert caplog.messages == ""

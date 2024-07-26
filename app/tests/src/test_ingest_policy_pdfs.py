import io
import logging
import tempfile

import pytest
from sqlalchemy import delete

from src.db.models.document import Document
from src.ingest_policy_pdfs import _ingest_policy_pdfs


@pytest.fixture
def policy_local_file():
    with tempfile.TemporaryDirectory() as tmpdirname:
        tempfile.NamedTemporaryFile(prefix="policy", suffix=".pdf", dir=tmpdirname, delete=False)
        yield tmpdirname


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
def test__ingest_policy_pdfs(
    caplog, app_config, db_session, policy_s3_file, policy_local_file, file_location
):
    db_session.execute(delete(Document))

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            _ingest_policy_pdfs(db_session, policy_local_file, doc_attribs)
        else:
            _ingest_policy_pdfs(db_session, policy_s3_file, doc_attribs)

        assert any(text.startswith("Processing pdf file:") for text in caplog.messages)

import logging

import pytest
from smart_open import open
from sqlalchemy import delete

from src.db.models.document import Document
from src.ingest_policy_pdfs import _ingest_policy_pdfs


@pytest.fixture
def policy_local_file():
    return "/app/tests/docs/"


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource):
    data = open("/app/tests/docs/policy_pdf.pdf", "rb")
    mock_s3_bucket_resource.put_object(Body=data, Key="policy_pdf.pdf")
    return "s3://test_bucket/"


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

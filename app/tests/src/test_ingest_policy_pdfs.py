import logging

import pytest
from smart_open import open
from sqlalchemy import delete, select

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
            _ingest_policy_pdfs(policy_local_file, doc_attribs)
        else:
            _ingest_policy_pdfs(policy_s3_file, doc_attribs)

        assert any(text.startswith("Processing pdf file:") for text in caplog.messages)
        documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
        assert set(d.dataset for d in documents) == {"test_dataset"}
        assert set(d.program for d in documents) == {"test_benefit_program"}
        assert set(d.region for d in documents) == {"Michigan"}

        assert documents[0].name == "BEM 105: MEDICAID OVERVIEW"
        assert "BPB 2024-001" in documents[0].content
        assert len(documents[0].chunks) == 1
        assert documents[0].chunks[0].tokens == 62
        assert "Social Security" in documents[0].chunks[0].content

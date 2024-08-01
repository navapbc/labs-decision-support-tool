import io
import logging
import tempfile

import pytest
from sqlalchemy import delete

from src.db.models.document import Document
from src.ingest_policy_pdfs import _ingest_policy_pdfs


@pytest.fixture
def sample_text():
    return """
    BEM 800 
    
    8 of 22 
    
    DISASTER ASSISTANCE 
    
    BPB 2023-024 
    
    10-1-2023 
    Applicants must have been evacuated from their home or forced to relocate in order to receive a payment. The family cannot be resid-ing in the home where the disaster occurred at the time of applica-tion. 
    """


@pytest.fixture
def policy_local_file(sample_text):
    with tempfile.TemporaryDirectory() as tmpdirname:
        with tempfile.NamedTemporaryFile(
            prefix="policy", suffix=".pdf", dir=tmpdirname, delete=False
        ) as tf:
            tf.write(sample_text)
        yield tmpdirname


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource, sample_text):
    bytes_text = sample_text.encode("utf-8")
    mock_s3_bucket_resource.put_object(Body=io.BytesIO(bytes_text), Key="policy.pdf")
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

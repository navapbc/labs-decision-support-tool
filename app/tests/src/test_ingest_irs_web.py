import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete, select

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_irs_web import _ingest_irs_web


@pytest.fixture
def sample_markdown():
    return json.dumps(
        [
        ]
    )


@pytest.fixture
def irs_web_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


doc_attribs = {
    "dataset": "IRS",
    "program": "tax credit",
    "region": "US",
}


def test_ingestion(caplog, app_config, db_session, irs_web_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="irs_web_md") as md_base_dir:
        with caplog.at_level(logging.WARNING):
            _ingest_irs_web(
                db_session,
                irs_web_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )

        # check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            _ingest_irs_web(
                db_session,
                irs_web_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )


def check_database_contents(db_session, caplog):
    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 3

    assert documents[0].name == "CALFRESH: 63-300 Application Process"
    assert (
        documents[0].source
        == "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm"
    )

    assert documents[1].name == "CalWORKs: 44-115 Income-In-Kind"
    assert (
        documents[1].source
        == "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-115_Inkind_Income/44-115_Inkind_Income.htm"
    )

    assert documents[2].name == "CalWORKs: 44-133 Treatment of Income"
    assert (
        documents[2].source
        == "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-133_Treatment_of_Income/44-133_Treatment_of_Income.htm"
    )

    doc0 = documents[0]
    assert len(doc0.chunks) == 2
    assert doc0.chunks[0].content.startswith("## 63-300 Application Process\n\n### Purpose\n\n")
    assert doc0.chunks[0].headings == ["CALFRESH"]
    assert doc0.chunks[1].content.startswith("# CALFRESH")
    assert doc0.chunks[1].headings == []

    # Document[1] is short
    doc1 = documents[1]
    assert len(doc1.chunks) == 1
    assert doc1.chunks[0].content.startswith("# CalWORKs\n\n## 44-115 Income-In-Kind\n\n")
    assert doc1.chunks[0].headings == []

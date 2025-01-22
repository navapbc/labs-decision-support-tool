import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete, select

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_runner import generalized_ingest, get_ingester_config


@pytest.fixture
def sample_markdown():
    return json.dumps(
        [
            {
                "url": "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm",
                "title": "63-300 Application Process",
                "h1": "CALFRESH",
                "h2": "63-300 Application Process",
                "markdown": """
# CALFRESH

## 63-300 Application Process

### Purpose

( ) To release a new policy

( ) To release a new form

( X ) To convert existing policy to new writing style only - No concept changes

( X ) Revision of existing policy and/or form(s).
""",
            },
            {
                "url": "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-133_Treatment_of_Income/44-133_Treatment_of_Income.htm",
                "title": "44-133 Treatment of Income-v1",
                "h1": "CalWORKs",
                "h2": "44-133 Treatment of Income",
                "markdown": """
# CalWORKs

## 44-133 Treatment of Income

### Requirements

All income must be reported to the County during the:

  * Intake process;
  * Redetermination interview;
  * On the SAR 7 report; and
  * As a mid-period report.""",
            },
            {
                "url": "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-115_Inkind_Income/44-115_Inkind_Income.htm",
                "title": "44-115 Inkind Income",
                "h1": "CalWORKs",
                "h2": "44-115 Income-In-Kind",
                "markdown": """
# CalWORKs

## 44-115 Income-In-Kind

### Background

In accordance with the Welfare and Institution Code 11453, IIK levels are to be adjusted annually to reflect any increases or decreases in COLA.""",
            },
        ]
    )


@pytest.fixture
def la_county_policy_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


def test_ingestion(caplog, app_config, db_session, la_county_policy_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="la_policy_md") as md_base_dir:
        config = get_ingester_config("DPSS Policy")
        with caplog.at_level(logging.WARNING):
            generalized_ingest(
                db_session,
                la_county_policy_local_file,
                config,
                md_base_dir=md_base_dir,
                resume=True,
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            generalized_ingest(
                db_session,
                la_county_policy_local_file,
                config,
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

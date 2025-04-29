import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete, select

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_runner import get_ingester_config
from src.ingester import ingest_json


@pytest.fixture
def sample_markdown():  # noqa: F811
    return json.dumps(
        [
            {
                "url": "https://keepyourbenefits.org/en/ca/",
                "title": "CALIFORNIA - Public Charge, Benefits and Immigration",
                "markdown": "### Who is affected by the Public Charge Rule?\n\n* It does not apply to:\n- U.S. Citizens or people applying for citizenship.  \n  - Lawful Permanent residents (Green Card holders) unless the Green Card holder leaves the U.S. for more than 6 months. A Public Charge assessment can apply when they try to return.  \n  - People applying for Green Card renewal or DACA renewal.",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/public-charge",
                "title": "CALIFORNIA - Public Charge Explained",
                "markdown": "### Public Benefits are part of the Public Charge Test\n\nOnly these public benefits* obtained for the immigrant are considered in the Public Charge Test. \n\n* • Cash benefits for income maintenance  \n   - SSI (Supplemental Security Income)  \n   - CalWorks/TANF (Temporary Assistance for Needy Families)  \n   - CAPI (Cash Assistance Programs for Immigrants)  \n   - GA (General Assistance/Relief)",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/resources",
                "title": "CALIFORNIA - FAQ and Resources: What is Public Charge",
                "markdown": "#### FAQs and Resources\n\nWhat is Public Charge and what benefits are included? \n\nFind answers and information sources to these and other public charge questions\n\n[Understanding Public Charge](https://keepyourbenefits.org/en/ca/resources/public-charge)\n#### Frequently Asked Questions\n\n\n Learn more before making decisions about public benefits for you and your family. Here are a few Frequently Asked Questions to get you started:\n\n**Q. What are public benefits?**\n\n\n A. Public benefits are government benefits like food, cash, housing, and medical assistance for people with low or no income. ",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/updates",
                "title": "CALIFORNIA - News Updates (English)",
                "markdown": '##### Nov 12, 2024: Important Update for Immigrant Families\n\n\nDespite the recent election, no immigration or public benefits rules have changed or are likely to change before January 20, 2025. We are closely monitoring any policy changes and will keep this page current with the latest information. Please check back here for updates and reliable guidance.\n\n  \n\n##### Nov 12, 2024: Deferred Action for Childhood Arrivals (DACA) Health Coverage Update\n\nStarting November 1, 2024, people with DACA status can sign up for health and dental plans through Covered California. Those who qualify may get help paying for their plan.\n\nDACA recipients have a special enrollment period from November 1 to December 31, 2024. To sign up, select "gained lawful presence" on the application. If you enroll in November, your coverage could start as soon as December 1, 2024.\n\nThis special enrollment period overlaps with Covered California’s open enrollment.',
            },
        ]
    )


def check_database_contents(db_session, caplog):
    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 4

    assert documents[0].name == "CALIFORNIA - FAQ and Resources: What is Public Charge"
    assert documents[0].source == "https://keepyourbenefits.org/en/ca/resources"

    assert documents[1].name == "CALIFORNIA - News Updates (English)"
    assert documents[1].source == "https://keepyourbenefits.org/en/ca/updates"

    assert documents[2].name == "CALIFORNIA - Public Charge, Benefits and Immigration"
    assert documents[2].source == "https://keepyourbenefits.org/en/ca/"

    doc0 = documents[0]
    assert len(doc0.chunks) == 2

    assert doc0.chunks[0].content.startswith("#### Frequently Asked Questions")
    assert doc0.chunks[0].headings == ["CALIFORNIA - FAQ and Resources: What is Public Charge"]
    assert doc0.chunks[1].content.startswith(
        "#### FAQs and Resources\n\nWhat is Public Charge and what benefits are included"
    )
    assert doc0.chunks[1].headings == ["CALIFORNIA - FAQ and Resources: What is Public Charge"]

    # # Document[1] is short
    doc1 = documents[1]
    assert len(doc1.chunks) == 3
    assert doc1.chunks[0].content.startswith(
        "##### Nov 12, 2024: Important Update for Immigrant Families"
    )
    assert doc1.chunks[0].headings == ["CALIFORNIA - News Updates (English)"]


@pytest.fixture
def ca_public_charge_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "ca_public_charge_web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


def test_ingestion(caplog, app_config, db_session, ca_public_charge_local_file):
    app_config_for_test.embedding_model.max_seq_length = 75

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="ca_public_charge_md") as md_base_dir:
        config = get_ingester_config("ca_public_charge")
        with caplog.at_level(logging.WARNING):
            ingest_json(
                db_session,
                ca_public_charge_local_file,
                config,
                md_base_dir=md_base_dir,
                resume=True,
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            ingest_json(
                db_session,
                ca_public_charge_local_file,
                config,
                md_base_dir=md_base_dir,
                resume=True,
            )

    skipped_logs = {
        msg for msg in caplog.messages if msg.startswith("Skipping -- document already exists")
    }
    assert len(skipped_logs) == 4
    assert db_session.query(Document.id).count() == 4

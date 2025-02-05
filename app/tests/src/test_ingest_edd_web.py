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
def sample_cards():
    return json.dumps(
        [
            {
                "url": "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/",
                "title": "Options to File for Disability Insurance Benefits",
                "main_content": "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you are eligible to [file a claim](/en/disability/apply/), review ...",
            },
            {
                "url": "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/",
                "title": "Options to File for Disability Insurance Benefits",
                "main_content": "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you are eligible to [file a claim](/en/disability/apply/), review ...",
            },
            {
                "url": "https://edd.ca.gov/en/disability/nonindustrial/faqs/",
                "title": "Nonindustrial Disability Insurance FAQs",
                "main_content": """## Nonindustrial Disability Insurance\n\nGet answers to FAQs about Nonindustrial Disability Insurance (NDI) and Nonindustrial Disability Insurance-Family Care Leave (NDI-FCL).

## Can I participate in either State Disability Insurance (SDI), NDI, or Enhanced Nonindustrial Insurance (ENDI)?

No. You cannot choose your disability program. It is determined by your employment position and bargaining unit.

## Will the State continue to contribute to my health, dental, and vision benefits if I am unable to work and receive NDI benefits?

If you are enrolled in the Annual Leave Program (ALP), your employer will continue to pay benefits.
""",
                "nonaccordion": "## Nonindustrial Disability Insurance\n\nGet answers to FAQs about Nonindustrial Disability Insurance (NDI) and Nonindustrial Disability Insurance-Family Care Leave (NDI-FCL).",
                "accordions": {
                    "Can I participate in either State Disability Insurance (SDI), NDI, or Enhanced Nonindustrial Insurance (ENDI)?": [
                        "No. You cannot choose your disability program. It is determined by your employment position and bargaining unit."
                    ],
                    "Will the State continue to contribute to my health, dental, and vision benefits if I am unable to work and receive NDI benefits?": [
                        "If you are enrolled in the Annual Leave Program (ALP), your employer will continue to pay benefits."
                    ],
                },
            },
            {
                "url": "https://edd.ca.gov/en/payroll_taxes/suta_dumping/",
                "title": "State Unemployment Tax Act Dumping",
                "main_content": (
                    "### SUTA Dumping Hurts Everyone\n\n"
                    "Employers, employees, and taxpayers make up the difference in higher taxes, lost jobs, lost profits, lower wages, and higher costs for goods and services.\n\n"
                    "SUTA dumping:\n\n"
                    "* Costs the UI trust fund millions of dollars each year.\n"
                    "* Adversely affects tax rates for all employers.\n"
                    "* Creates inequity for compliant employers.\n"
                    "* Eliminates the incentive for employers to avoid layoffs.\n"
                    "* Compromises the integrity of the UI system.\n\n"
                    "### [SUTA Dumping Schemes](https://edd.ca.gov/en/payroll_taxes/suta_dumping/#collapse-2a82e068-3b29-4473-af7e-de9ea6961277)\n\n"
                    "These schemes are meant to unlawfully lower an employer\u2019s UI tax rate. Employers should know about these schemes and their potential legal ramifications.\n\n"
                ),
            },
            {
                "url": "https://edd.ca.gov/en/jobs_and_training/northern_region/",
                "title": "The Northern Job Fairs and Workshops",
                "main_primary": (
                    "## Scheduled Events\n\n"
                    "**Career Center Orientation**\n"
                    "| Location | Date/Time | Other Information |\n"
                    "| --- | --- | --- |\n"
                    "| Virtual | Friday | This workshop will ... |\n"
                    "| Virtual | Friday | This workshop is for ... |\n"
                    "| Virtual | Friday | Staff will conduct ... |\n"
                ),
            },
        ]
    )


@pytest.fixture
def edd_web_local_file(tmp_path, sample_cards):
    file_path = tmp_path / "edd_scrapings.json"
    file_path.write_text(sample_cards)
    return str(file_path)


@pytest.fixture
def edd_web_s3_file(mock_s3_bucket_resource, sample_cards):
    mock_s3_bucket_resource.put_object(Body=sample_cards, Key="edd_scrapings.json")
    return "s3://test_bucket/edd_scrapings.json"


def test__ingest_edd_using_md_tree(caplog, app_config, db_session, edd_web_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="edd_md") as md_base_dir:
        config = get_ingester_config("edd")
        with caplog.at_level(logging.WARNING):
            ingest_json(
                db_session, edd_web_local_file, config, md_base_dir=md_base_dir, resume=True
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            ingest_json(
                db_session, edd_web_local_file, config, md_base_dir=md_base_dir, resume=True
            )

    skipped_logs = {
        msg for msg in caplog.messages if msg.startswith("Skipping -- document already exists")
    }
    assert len(skipped_logs) == 4
    assert db_session.query(Document.id).count() == 4


def check_database_contents(db_session, caplog):
    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 4

    assert (
        "Skipping duplicate URL: https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/"
        in caplog.messages[0]
    )

    assert documents[0].name == "Nonindustrial Disability Insurance FAQs"
    assert documents[0].source == "https://edd.ca.gov/en/disability/nonindustrial/faqs/"
    assert documents[1].name == "Options to File for Disability Insurance Benefits"
    assert (
        documents[1].source == "https://edd.ca.gov/en/disability/options_to_file_for_di_benefits/"
    )
    assert documents[2].name == "State Unemployment Tax Act Dumping"
    assert documents[2].source == "https://edd.ca.gov/en/payroll_taxes/suta_dumping/"
    assert documents[3].name == "The Northern Job Fairs and Workshops"
    assert documents[3].source == "https://edd.ca.gov/en/jobs_and_training/northern_region/"

    # Document[0] has 3 sections, each section becomes its own chunk
    doc0 = documents[0]
    assert len(doc0.chunks) == 3
    assert doc0.chunks[0].content.startswith(
        "## Can I participate in either State Disability Insurance (SDI)"
    )
    assert doc0.chunks[1].content.startswith(
        "## Will the State continue to contribute to my health, dental,"
    )
    assert doc0.chunks[2].content.startswith("## Nonindustrial Disability Insurance\n\n")
    # All chunks have the same heading
    for chunk in doc0.chunks:
        assert chunk.headings == ["Nonindustrial Disability Insurance FAQs"]

    # Document[1] is short
    doc1 = documents[1]
    assert len(doc1.chunks) == 1
    assert doc1.chunks[0].content.startswith(
        "Disability Insurance (DI) provides short-term, partial wage replacement ...\n\nIf you think you"
    )
    assert doc1.chunks[0].headings == ["Options to File for Disability Insurance Benefits"]

    # Document[2] has a list
    doc2 = documents[2]
    assert len(doc2.chunks) == 4

    # First section
    assert doc2.chunks[0].headings == ["State Unemployment Tax Act Dumping"]
    assert doc2.chunks[0].content.startswith(
        "### SUTA Dumping Hurts Everyone\n\nEmployers, employees, and taxpayers"
    )

    # List is split into two chunks
    assert (
        doc2.chunks[1].headings
        == doc2.chunks[2].headings
        == [
            "State Unemployment Tax Act Dumping",
            "SUTA Dumping Hurts Everyone",
        ]
    )
    assert doc2.chunks[1].content.startswith("SUTA dumping:\n\n* Costs the UI")
    assert doc2.chunks[2].content.startswith(
        "(SUTA dumping:)\n\n* Compromises the integrity of the UI system."
    )

    # Last section
    assert doc2.chunks[3].headings == ["State Unemployment Tax Act Dumping"]
    assert doc2.chunks[3].content.startswith("### [SUTA Dumping Schemes]")

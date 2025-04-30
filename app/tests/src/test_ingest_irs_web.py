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
def sample_markdown():
    return json.dumps(
        [
            {
                "url": "https://www.irs.gov/credits-deductions/family-dependents-and-students-credits",
                "title": "Family, dependents and students credits",
                "markdown": """Credits can help reduce your taxes or increase your refund.

## Earned Income Tax Credit (EITC)

[The Earned Income Tax Credit (EITC)](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit-eitc "Earned Income Tax Credit (EITC)") helps low- to moderate-income workers and families.
""",
            },
            {
                "url": "https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit-eitc",
                "title": "Earned Income Tax Credit (EITC)",
                "markdown": """### More In Credits & Deductions

__

  * [Family, dependents and students](https://www.irs.gov/credits-deductions/family-dependents-and-students-credits "Family, dependents and students")
    * [Earned Income Tax Credit](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit-eitc "Earned Income Tax Credit")
      * [EITC Qualification Assistant](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit/use-the-eitc-assistant "EITC Qualification Assistant")
      * [Who qualifies for the EITC](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit/who-qualifies-for-the-earned-income-tax-credit-eitc "Who qualifies for the EITC")
      * [Qualifying child or relative for the EITC](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit/qualifying-child-rules "Qualifying child or relative for the EITC")
      * [Earned income and credit tables](https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit/earned-income-and-earned-income-tax-credit-eitc-tables "Earned income and credit tables")
    * [Child Tax Credit](https://www.irs.gov/credits-deductions/individuals/child-tax-credit "Child Tax Credit")
    * [Educational credits](https://www.irs.gov/credits-deductions/individuals/education-credits-aotc-llc "Educational credits")
  * [Clean energy and vehicle credits](https://www.irs.gov/credits-deductions/clean-vehicle-and-energy-credits "Clean energy and vehicle credits")
  * [Individuals credits and deductions](https://www.irs.gov/credits-and-deductions-for-individuals "Individuals credits and deductions")
  * [Business credits and deductions](https://www.irs.gov/credits-deductions/businesses "Business credits and deductions")""",
            },
        ]
    )


@pytest.fixture
def irs_web_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


def test_ingestion(caplog, app_config, db_session, irs_web_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.embedding_model.max_seq_length = 47

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="irs_web_md") as md_base_dir:
        config = get_ingester_config("irs")
        with caplog.at_level(logging.WARNING):
            ingest_json(
                db_session,
                irs_web_local_file,
                config,
                md_base_dir=md_base_dir,
                resume=True,
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            ingest_json(
                db_session,
                irs_web_local_file,
                config,
                md_base_dir=md_base_dir,
                resume=True,
            )


def check_database_contents(db_session, caplog):
    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 2

    assert documents[0].name == "Earned Income Tax Credit (EITC)"
    assert (
        documents[0].source
        == "https://www.irs.gov/credits-deductions/individuals/earned-income-tax-credit-eitc"
    )

    assert documents[1].name == "Family, dependents and students credits"
    assert (
        documents[1].source
        == "https://www.irs.gov/credits-deductions/family-dependents-and-students-credits"
    )

    doc0 = documents[0]
    assert len(doc0.chunks) == 2
    assert doc0.chunks[0].content.startswith("### More In Credits & Deductions\n\n")
    assert doc0.chunks[0].headings == ["Earned Income Tax Credit (EITC)"]
    assert doc0.chunks[1].content.startswith(
        "__\n\n* * [Child Tax Credit](https://www.irs.gov/credits-deductions/individuals/child-tax-credit"
    )
    assert doc0.chunks[1].headings == ["Earned Income Tax Credit (EITC)"]

    doc1 = documents[1]
    assert len(doc1.chunks) == 1
    assert doc1.chunks[0].content.startswith(
        "Credits can help reduce your taxes or increase your refund.\n\n"
    )
    assert doc1.chunks[0].headings == ["Family, dependents and students credits"]

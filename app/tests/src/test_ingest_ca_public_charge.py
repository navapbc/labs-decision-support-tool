import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_ca_public_charge import _ingest_ca_public_charge

from .test_ingest_edd_web import check_database_contents  # noqa: F401


@pytest.fixture
def sample_markdown():  # noqa: F811
    return json.dumps(
        [
            {
                "url": "https://keepyourbenefits.org/en/ca/",
                "title": "CALIFORNIA - Public Charge, Benefits and Immigration",
                "markdown": "\n### Who is affected by the Public Charge Rule?\n\n* It does not apply to:\n- U.S. Citizens or people applying for citizenship.  \n  - Lawful Permanent residents (Green Card holders) unless the Green Card holder leaves the U.S. for more than 6 months. A Public Charge assessment can apply when they try to return.",
                "main_content": "\n### Who is affected by the Public Charge Rule?\n\n* It does not apply to:\n- U.S. Citizens or people applying for citizenship.  \n  - Lawful Permanent residents (Green Card holders) unless the Green Card holder leaves the U.S. for more than 6 months. A Public Charge assessment can apply when they try to return.",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/public-charge",
                "title": "CALIFORNIA - Public Charge Explained",
                "markdown": "\n### Public Benefits are part of the Public Charge Test\n\nOnly these public benefits* obtained for the immigrant are considered in the Public Charge Test. \n\n* • Cash benefits for income maintenance  \n   - SSI (Supplemental Security Income)  \n   - CalWorks/TANF (Temporary Assistance for Needy Families)  \n   - CAPI (Cash Assistance Programs for Immigrants)  \n   - GA (General Assistance/Relief)  - Medi-Cal/Medicaid for long-term, medical care in an institution, like a nursing home or psychiatric hospital",
                "main_content": "\n### Public Benefits are part of the Public Charge Test\n\nOnly these public benefits* obtained for the immigrant are considered in the Public Charge Test. \n\n* • Cash benefits for income maintenance  \n   - SSI (Supplemental Security Income)  \n   - CalWorks/TANF (Temporary Assistance for Needy Families)  \n   - CAPI (Cash Assistance Programs for Immigrants)  \n   - GA (General Assistance/Relief)  - Medi-Cal/Medicaid for long-term, medical care in an institution, like a nursing home or psychiatric hospital",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/resources",
                "title": "CALIFORNIA - FAQ and Resources: What is Public Charge",
                "markdown": "\n#### FAQs and Resources\n\nWhat is Public Charge and what benefits are included? \n\nFind answers and information sources to these and other public charge questions\n\n[Understanding Public Charge](https://keepyourbenefits.org/en/ca/resources/public-charge)\n#### Frequently Asked Questions\n\n\r\n Learn more before making decisions about public benefits for you and your family. Here are a few Frequently Asked Questions to get you started:\r\n\n**Q. What are public benefits?**\n\n\r\n A. Public benefits are government benefits like food, cash, housing, and medical assistance for people with low or no income. Examples include CalFresh/SNAP (food stamps), CalWORKs/TANF, Public Housing, Section 8, and Medi-Cal/Medicaid.",
                "main_content": "\n#### FAQs and Resources\n\nWhat is Public Charge and what benefits are included? \n\nFind answers and information sources to these and other public charge questions\n\n[Understanding Public Charge](https://keepyourbenefits.org/en/ca/resources/public-charge)\n#### Frequently Asked Questions\n\n\r\n Learn more before making decisions about public benefits for you and your family. Here are a few Frequently Asked Questions to get you started:\r\n\n**Q. What are public benefits?**\n\n\r\n A. Public benefits are government benefits like food, cash, housing, and medical assistance for people with low or no income. Examples include CalFresh/SNAP (food stamps), CalWORKs/TANF, Public Housing, Section 8, and Medi-Cal/Medicaid.",
            },
            {
                "url": "https://keepyourbenefits.org/en/ca/updates",
                "title": "CALIFORNIA - News Updates (English)",
                "markdown": "\n##### Nov 12, 2024: Important Update for Immigrant Families\n\n\r\nDespite the recent election, no immigration or public benefits rules have changed or are likely to change before January 20, 2025. We are closely monitoring any policy changes and will keep this page current with the latest information.",
                "main_content": "\n##### Nov 12, 2024: Important Update for Immigrant Families\n\n\r\nDespite the recent election, no immigration or public benefits rules have changed or are likely to change before January 20, 2025. We are closely monitoring any policy changes and will keep this page current with the latest information.",
            },
        ]
    )


@pytest.fixture
def ca_public_charge_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "ca_public_charge_web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


doc_attribs = {
    "dataset": "Keep Your Benefits",
    "program": "mixed",
    "region": "California",
}


def test_ingestion(caplog, app_config, db_session, ca_public_charge_local_file):
    app_config_for_test.sentence_transformer.max_seq_length = 75

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="ca_public_charge_md") as md_base_dir:
        with caplog.at_level(logging.WARNING):
            _ingest_ca_public_charge(
                db_session,
                ca_public_charge_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            _ingest_ca_public_charge(
                db_session,
                ca_public_charge_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )

    skipped_logs = {
        msg for msg in caplog.messages if msg.startswith("Skipping -- document already exists")
    }
    assert len(skipped_logs) == 4
    assert db_session.query(Document.id).count() == 4

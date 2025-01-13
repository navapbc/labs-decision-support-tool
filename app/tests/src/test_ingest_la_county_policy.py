import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_la_county_policy import _ingest_la_county_policy

from .test_ingest_edd_web import check_database_contents, sample_cards  # noqa: F401


@pytest.fixture
def sample_markdown(sample_cards):  # noqa: F811
    items = json.loads(sample_cards)
    for item in items:
        item["h1"] = "Test Benefit Program"
        item["h2"] = item["title"]
        item["markdown"] = item.get("main_content", item.get("main_primary"))
    return json.dumps(items)


@pytest.fixture
def la_county_policy_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


doc_attribs = {
    "dataset": "DPSS Policy",
    "program": "mixed",
    "region": "California:LA County",
}


def test_ingestion(caplog, app_config, db_session, la_county_policy_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

    db_session.execute(delete(Document))

    with TemporaryDirectory(suffix="la_policy_md") as md_base_dir:
        with caplog.at_level(logging.WARNING):
            _ingest_la_county_policy(
                db_session,
                la_county_policy_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )

        check_database_contents(db_session, caplog)

        # Re-ingesting the same data should not add any new documents
        with caplog.at_level(logging.INFO):
            _ingest_la_county_policy(
                db_session,
                la_county_policy_local_file,
                doc_attribs,
                md_base_dir=md_base_dir,
                resume=True,
            )

    skipped_logs = {
        msg for msg in caplog.messages if msg.startswith("Skipping -- document already exists")
    }
    assert len(skipped_logs) == 4
    assert db_session.query(Document.id).count() == 4

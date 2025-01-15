import json
import logging
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import delete

from src.app_config import app_config as app_config_for_test
from src.db.models.document import Document
from src.ingest_ca_public_charge import _ingest_ca_public_charge

from .test_ingest_edd_web import check_database_contents, sample_cards  # noqa: F401


@pytest.fixture
def sample_markdown(sample_cards):  # noqa: F811
    items = json.loads(sample_cards)
    for item in items:
        item["h4"] = item["title"]
        item["markdown"] = item.get("main_content", item.get("main_primary"))
    return json.dumps(items)


@pytest.fixture
def ca_public_charge_local_file(tmp_path, sample_markdown):
    file_path = tmp_path / "ca_public_charge_web_scrapings.json"
    file_path.write_text(sample_markdown)
    return str(file_path)


doc_attribs = {
    "dataset": "keepyourbenefits.org",
    "program": "mixed",
    "region": "California",
}


def test_ingestion(caplog, app_config, db_session, ca_public_charge_local_file):
    # Force a short max_seq_length to test chunking
    app_config_for_test.sentence_transformer.max_seq_length = 47

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

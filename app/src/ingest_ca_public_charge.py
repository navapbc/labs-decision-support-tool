import logging
import sys

from src.adapters import db
from src.ingest_edd_web import (  # TODO: move ingest_json() to ingest_utils.py
    _fix_input_markdown,
    ingest_json,
)
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_ca_public_charge(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str = "ca_public_charge_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    def prep_json_item(item: dict[str, str]) -> None:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = _fix_input_markdown(markdown)

    common_base_url = "https://keepyourbenefits.org/en/ca/"
    ingest_json(
        db_session,
        json_filepath,
        doc_attribs,
        md_base_dir,
        common_base_url,
        skip_db,
        resume,
        prep_json_item,
    )


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_ca_public_charge)

import logging
import sys

from src.adapters import db
from src.ingest_edd_web import ingest_json
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_wic(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str = "wic_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    common_base_url = "https://www.phfewic.org/"

    ingest_json(
        db_session,
        json_filepath,
        doc_attribs,
        md_base_dir,
        common_base_url,
        skip_db,
        resume,
    )


def main() -> None:  # pragma: no cover
    process_and_ingest_sys_args(sys.argv, logger, _ingest_wic)

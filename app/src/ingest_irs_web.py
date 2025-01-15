import logging
import sys

from src.adapters import db
from src.ingest_edd_web import ingest_json
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_irs_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str = "irs_web_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    common_base_url = "https://www.irs.gov/"

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
    process_and_ingest_sys_args(sys.argv, logger, _ingest_irs_web)

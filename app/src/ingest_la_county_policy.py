import logging
import sys

from src.adapters import db
from src.ingest_edd_web import ingest_json  # TODO: move ingest_json() to ingest_utils.py
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_la_county_policy(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str = "la_policy_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    def prep_json_item(item: dict[str, str]) -> dict[str, str]:
        # More often than not, the h2 heading is better suited as the title
        item["title"] = item["h2"]
        return item

    common_base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/"
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
    process_and_ingest_sys_args(sys.argv, logger, _ingest_la_county_policy)

import logging
import sys

from src.adapters import db

# TODO: move ingest_json() to ingest_utils.py
from src.ingest_edd_web import ingest_json
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


common_base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/"


def _ingest_la_county_policy(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    resume: bool = False,
) -> None:
    def prep_json_item(item: dict[str, str]) -> dict[str, str]:
        # More often than not, the h2 heading is better suited as the title
        item["title"] = item["h2"]
        return item

    ingest_json(db_session, json_filepath, doc_attribs, resume, prep_json_item)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_la_county_policy)

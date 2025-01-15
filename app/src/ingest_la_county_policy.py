import logging
import sys

from src.adapters import db
from src.ingest_edd_web import ingest_json  # TODO: move ingest_json() to ingest_utils.py
from src.util.ingest_utils import DefaultChunkingConfig, process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_la_county_policy(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    md_base_dir: str = "la_policy_md",
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    common_base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/"

    def prep_json_item(item: dict[str, str]) -> None:
        # More often than not, the h2 heading is better suited as the title
        item["title"] = item["h2"]

        # Include the program name in the document title
        program_name = item["h1"]
        item["title"] = f"{program_name}: {item['title']}"

    chunking_config = DefaultChunkingConfig()
    # The document name is the same as item["h2"], so it is redundant to include it in the headings
    chunking_config.include_doc_name_in_headings = False
    ingest_json(
        db_session,
        json_filepath,
        doc_attribs,
        md_base_dir,
        common_base_url,
        skip_db,
        resume,
        prep_json_item,
        chunking_config,
    )


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_la_county_policy)

import argparse
import logging
import re
import sys
from typing import Callable, NamedTuple, Optional

from src.adapters import db
from src.ingester import ingest_json
from src.util.ingest_utils import ChunkingConfig, DefaultChunkingConfig, start_ingestion

logger = logging.getLogger(__name__)


class IngestConfig(NamedTuple):
    dataset_id: str
    benefit_program: str
    benefit_region: str
    common_base_url: str
    md_base_dir: str
    prep_json_item: Optional[Callable[[dict[str, str]], None]] = None
    chunking_config: Optional[ChunkingConfig] = None


def edd_web_config(dataset_id: str, benefit_program: str, benefit_region: str) -> IngestConfig:
    def _fix_input_markdown(markdown: str) -> str:
        # Fix ellipsis text that causes markdown parsing errors
        # '. . .' is parsed as sublists on the same line
        # in https://edd.ca.gov/en/uibdg/total_and_partial_unemployment_tpu_5/
        markdown = markdown.replace(". . .", "...")

        # Nested sublist '* + California's New Application' created without parent list
        # in https://edd.ca.gov/en/about_edd/eddnext
        markdown = markdown.replace("* + ", "    + ")

        # Blank sublist '* ###" in https://edd.ca.gov/en/unemployment/Employer_Information/
        # Tab labels are parsed into list items with headings; remove them
        markdown = re.sub(r"^\s*\* #+", "", markdown, flags=re.MULTILINE)

        # Blank sublist '* +" in https://edd.ca.gov/en/unemployment/Employer_Information/
        # Empty sublist '4. * ' in https://edd.ca.gov/en/about_edd/your-benefit-payment-options/
        # Remove empty nested sublists
        markdown = re.sub(
            r"^\s*(\w+\.|\*|\+|\-) (\w+\.|\*|\+|\-)\s*$", "", markdown, flags=re.MULTILINE
        )
        return markdown

    def prep_json_item(item: dict[str, str]) -> None:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = _fix_input_markdown(markdown)

    return IngestConfig(
        dataset_id,
        benefit_program,
        benefit_region,
        "https://edd.ca.gov/en/",
        "edd_web_md",
        prep_json_item,
    )


def la_county_policy_config(
    dataset_id: str, benefit_program: str, benefit_region: str
) -> IngestConfig:
    chunking_config = DefaultChunkingConfig()
    # The document name is the same as item["h2"], so it is redundant to include it in the headings
    chunking_config.include_doc_name_in_headings = False

    def prep_json_item(item: dict[str, str]) -> None:
        # More often than not, the h2 heading is better suited as the title
        item["title"] = item["h2"]

        # Include the program name in the document title
        program_name = item["h1"]
        item["title"] = f"{program_name}: {item['title']}"

    return IngestConfig(
        dataset_id,
        benefit_program,
        benefit_region,
        "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/",
        "la_policy_md",
        prep_json_item,
        chunking_config,
    )


def ca_public_charge_config(
    dataset_id: str, benefit_program: str, benefit_region: str
) -> IngestConfig:
    def prep_json_item(item: dict[str, str]) -> None:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = markdown

    return IngestConfig(
        dataset_id,
        benefit_program,
        benefit_region,
        "https://keepyourbenefits.org/en/ca/",
        "ca_public_charge_md",
        prep_json_item,
    )


def get_ingester_config(dataset_id: str) -> IngestConfig:
    match dataset_id:
        case "CA EDD":
            return edd_web_config(dataset_id, "unemployment insurance", "California")
        case "DPSS Policy":
            return la_county_policy_config(dataset_id, "mixed", "California:LA County")
        case "IRS":
            return IngestConfig(
                dataset_id, "tax credit", "US", "https://www.irs.gov/", "irs_web_md"
            )
        case "Keep Your Benefits":
            return ca_public_charge_config(dataset_id, "mixed", "California")
        case _:
            raise ValueError(f"Unknown dataset_id: {dataset_id}")


# Print INFO messages since this is often run from the terminal during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def generalized_ingest(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    *,
    md_base_dir: Optional[str] = None,
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    config = get_ingester_config(doc_attribs["dataset"])
    ingest_json(
        db_session,
        json_filepath,
        doc_attribs,
        md_base_dir or config.md_base_dir,
        config.common_base_url,
        skip_db=skip_db,
        resume=resume,
        prep_json_item=config.prep_json_item,
        chunking_config=config.chunking_config,
    )


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_id")
    parser.add_argument("file_path")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip_db", action="store_true")
    args = parser.parse_args(sys.argv[1:])

    config = get_ingester_config(sys.argv[1])
    doc_attribs = {
        "dataset": config.dataset_id,
        "program": config.benefit_program,
        "region": config.benefit_region,
    }
    start_ingestion(
        logger,
        generalized_ingest,
        args.file_path,
        doc_attribs,
        skip_db=args.skip_db,
        resume=args.resume,
    )

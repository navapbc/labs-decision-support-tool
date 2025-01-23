import argparse
import logging
import re
import sys

from src.ingester import ingest_json
from src.util.ingest_utils import DefaultChunkingConfig, IngestConfig, start_ingestion

logger = logging.getLogger(__name__)


def edd_web_config(
    dataset_label: str, benefit_program: str, benefit_region: str, scraper_dataset: str
) -> IngestConfig:
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
        dataset_label,
        benefit_program,
        benefit_region,
        "https://edd.ca.gov/en/",
        scraper_dataset,
        prep_json_item,
    )


def la_county_policy_config(
    dataset_label: str, benefit_program: str, benefit_region: str, scraper_dataset: str
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
        dataset_label,
        benefit_program,
        benefit_region,
        "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/",
        scraper_dataset,
        prep_json_item,
        chunking_config,
    )


def ca_public_charge_config(
    dataset_label: str, benefit_program: str, benefit_region: str, scraper_dataset: str
) -> IngestConfig:
    def prep_json_item(item: dict[str, str]) -> None:
        markdown = item.get("main_content", item.get("main_primary", None))
        assert markdown, f"Item {item['url']} has no main_content or main_primary"
        item["markdown"] = markdown

    return IngestConfig(
        dataset_label,
        benefit_program,
        benefit_region,
        "https://keepyourbenefits.org/en/ca/",
        scraper_dataset,
        prep_json_item,
    )


def get_ingester_config(scraper_dataset: str) -> IngestConfig:
    match scraper_dataset:
        case "ca_ftb":
            return IngestConfig(
                "CA FTB", "tax credit", "California", "https://www.ftb.ca.gov/", scraper_dataset
            )
        case "ca_public_charge":
            return ca_public_charge_config(
                "Keep Your Benefits", "mixed", "California", scraper_dataset
            )
        case "ca_wic":
            return IngestConfig(
                "WIC", "wic", "California", "https://www.phfewic.org/en/", scraper_dataset
            )
        case "edd":
            return edd_web_config("CA EDD", "employment", "California", scraper_dataset)
        case "irs":
            return IngestConfig("IRS", "tax credit", "US", "https://www.irs.gov/", scraper_dataset)
        case "la_policy":
            return la_county_policy_config(
                "DPSS Policy", "mixed", "California:LA County", scraper_dataset
            )
        case _:
            raise ValueError(
                f"Unknown dataset: {scraper_dataset!r}.  Run `make scrapy-runner` to see available datasets"
            )


# Print INFO messages since this is often run from the terminal during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="scraper dataset id from `make scrapy-runner`")
    parser.add_argument("--json_input", help="path to the JSON file to ingest")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip_db", action="store_true")
    args = parser.parse_args(sys.argv[1:])

    config = get_ingester_config(args.dataset)
    start_ingestion(
        logger,
        ingest_json,
        args.json_input or f"src/ingestion/{config.scraper_dataset}_scrapings.json",
        config,
        skip_db=args.skip_db,
        resume=args.resume,
    )

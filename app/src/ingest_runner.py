import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from src.ingester import ingest_json
from src.util.ingest_utils import DefaultChunkingConfig, IngestConfig, start_ingestion

logger = logging.getLogger(__name__)


def edd_config(
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


def la_policy_config(
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


def get_ingester_config(scraper_dataset: str) -> IngestConfig:  # pragma: no cover
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
        case "covered_ca":
            return IngestConfig(
                "Covered California",
                "insurance",
                "California",
                "https://www.coveredca.com/",
                scraper_dataset,
            )
        case "edd":
            return edd_config("CA EDD", "employment", "California", scraper_dataset)
        case "irs":
            return IngestConfig("IRS", "tax credit", "US", "https://www.irs.gov/", scraper_dataset)
        case "la_policy":
            return la_policy_config("DPSS Policy", "mixed", "California:LA County", scraper_dataset)
        case "ssa":
            return IngestConfig(
                "SSA", "social security", "US", "https://www.ssa.gov/", scraper_dataset
            )
        case _:
            raise ValueError(
                f"Unknown dataset: {scraper_dataset!r}.  Run `make scrapy-runner` to see available datasets"
            )


# Print INFO messages since this is often run from the terminal during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def merge_json_files(json_files: list[str], output_file: str) -> None:
    merged = []
    for json_file in json_files:
        json_items = json.loads(Path(json_file).read_text(encoding="utf-8"))
        logger.info("Loaded %d items from %r", len(json_items), json_file)
        merged.extend(json_items)
    logger.info("Merged %d files into %d items in %r", len(json_files), len(merged), output_file)
    Path(output_file).write_text(json.dumps(merged, indent=2), encoding="utf-8")


def conditionally_consolidate_json_files(json_files: list[str], outfile_prefix: str) -> str:
    if not json_files:
        return ""
    if len(json_files) == 1:
        return json_files[0]

    output_file = f"{outfile_prefix}_combined_scrapings.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    merge_json_files(json_files, output_file)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="scraper dataset id from `make scrapy-runner`")
    parser.add_argument("--json_input", help="path to the JSON file to ingest", action="append")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip_db", action="store_true")
    args = parser.parse_args(sys.argv[1:])

    config = get_ingester_config(args.dataset)

    output_file_prefix = os.path.join(config.md_base_dir, config.scraper_dataset)
    json_input = conditionally_consolidate_json_files(args.json_input, output_file_prefix)

    start_ingestion(
        logger,
        ingest_json,
        json_input or f"src/ingestion/{config.scraper_dataset}_scrapings.json",
        config,
        skip_db=args.skip_db,
        resume=args.resume,
    )

import json
import logging
import os
from pprint import pprint

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

logger = logging.getLogger(__name__)


# Typically, env variable SCRAPY_PROJECT should be set when calling this script.
# The SCRAPY_PROJECT env variable refers to the projects defined in scrapy.cfg
# and the folder that Scrapy uses to find Python files.
if "SCRAPY_PROJECT" not in os.environ:
    # This script is useful for postprocessing the json output.
    os.environ["SCRAPY_PROJECT"] = "scrapy_dst"

OUTPUT_JSON = "la_policy_scrapings.json"


def run_spider(spider_name: str) -> None:
    settings = get_project_settings()
    settings["FEEDS"] = {
        OUTPUT_JSON: {"format": "json"},
    }
    process = CrawlerProcess(settings)
    pprint(process.settings.copy_to_dict())

    # Remove the output file if it already exists so that Scrapy doesn't append to it
    if OUTPUT_JSON in os.listdir():
        os.remove(OUTPUT_JSON)

    # spider-name the name of one of the spiders (see *Spider.name)
    process.crawl(spider_name)
    process.start()  # the script will block here until the crawling is finished

    logger.info("Scraping results saved to %s", OUTPUT_JSON)


def postprocess_json() -> None:
    # Postprocess the JSON output for readability
    with open(OUTPUT_JSON, "r", encoding="utf-8") as raw_json:
        data = json.load(raw_json)

        # This code could be moved to pipelines.py to be more formal
        with open(f"pretty-{OUTPUT_JSON}", "w", encoding="utf-8") as formatted_json:
            formatted_json.write(json.dumps(data, indent=4))
            logger.info("Formatted JSON saved to pretty-%s", OUTPUT_JSON)


SPIDER_NAME = "la_policy_spider"


def main() -> None:
    # Scrapy expects the scrapy.cfg file to be in the current working directory
    os.chdir("src/ingestion")
    run_spider(SPIDER_NAME)

    if "DEBUG_SCRAPINGS" in os.environ:
        postprocess_json()


if __name__ == "__main__":
    run_spider(SPIDER_NAME)
    postprocess_json()

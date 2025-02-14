import argparse
import json
import logging
import os
import sys
from pprint import pprint

from scrapy import spiderloader
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

logger = logging.getLogger(__name__)


# Typically, env variable SCRAPY_PROJECT should be set when calling this script.
# The SCRAPY_PROJECT env variable refers to the projects defined in scrapy.cfg
# and the folder that Scrapy uses to find Python files.
if "SCRAPY_PROJECT" not in os.environ:
    # This script is useful for postprocessing the json output.
    os.environ["SCRAPY_PROJECT"] = "scrapy_dst"


def run_spider(spider_name: str, output_json_filename: str) -> None:
    settings = get_project_settings()
    settings["FEEDS"] = {
        output_json_filename: {"format": "json"},
    }
    process = CrawlerProcess(settings)
    pprint(process.settings.copy_to_dict())

    # Remove the output file if it already exists so that Scrapy doesn't append to it
    if output_json_filename in os.listdir():
        os.remove(output_json_filename)

    # spider-name the name of one of the spiders (see *Spider.name)
    process.crawl(spider_name)
    process.start()  # the script will block here until the crawling is finished

    logger.info("Scraping results saved to %s", os.path.realpath(output_json_filename))


def postprocess_json(input_filename: str) -> None:
    # Postprocess the JSON output for readability
    with open(input_filename, "r", encoding="utf-8") as raw_json:
        data = json.load(raw_json)

        # This code could be moved to pipelines.py to be more formal
        with open(f"{input_filename}-pretty.json", "w", encoding="utf-8") as formatted_json:
            formatted_json.write(json.dumps(data, indent=4))
            logger.info("Formatted JSON saved to %s-pretty.json", input_filename)


def list_spiders() -> list[str]:
    settings = get_project_settings()
    spider_loader = spiderloader.SpiderLoader.from_settings(settings)
    return spider_loader.list()


def main() -> None:
    # Scrapy expects the scrapy.cfg file to be in the current working directory
    if "src" in os.listdir():
        os.chdir("src/ingestion")

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--debug", action="store_true")

    if len(sys.argv) == 1:
        parser.print_help()
        print("")
        spiders = list_spiders()
        datasets = [spider.removesuffix("_spider") for spider in spiders]
        print(f"Available datasets: {datasets}")
        return

    args = parser.parse_args(sys.argv[1:])
    spider_id = f"{args.dataset}_spider"
    json_output = f"{spider_id.removesuffix('spider')}scrapings.json"

    run_spider(spider_id, json_output)
    if args.debug:
        postprocess_json(json_output)

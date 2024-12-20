# /// script
# dependencies = [
#   "install-playwright",
#   "playwright",
#   "scrapy",
#   "markdownify",
#   "nltk",
#   "langchain_text_splitters",
#   "html2text",
#   "mistletoe",
#   "nutree",
# ]
# ///
# (This comment enables `uv run` to automatically create a virtual environment)

SPIDER_NAME = "la_policy_spider"
OUTPUT_JSON = "la_policy_scrapings.json"


def main() -> None:
    import os

    from .scrapy_runner import run

    run(SPIDER_NAME, OUTPUT_JSON, debug=bool(os.environ["DEBUG_SCRAPINGS"]))


if __name__ == "__main__":
    from scrapy_runner import run

    run(SPIDER_NAME, OUTPUT_JSON, debug=True)

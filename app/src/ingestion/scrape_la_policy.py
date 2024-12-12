SPIDER_NAME = "la_policy_spider"
OUTPUT_JSON = "la_policy_scrapings.json"

def main() -> None:
    import os
    from .scrapy_runner import run
    run(SPIDER_NAME, OUTPUT_JSON, debug=bool(os.environ["DEBUG_SCRAPINGS"]))


if __name__ == "__main__":
    from scrapy_runner import run
    run(SPIDER_NAME, OUTPUT_JSON, debug=True)

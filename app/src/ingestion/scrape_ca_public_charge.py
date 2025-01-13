SPIDER_NAME = "ca_public_charge_spider"
OUTPUT_JSON = "ca_public_charge_scrapings.json"


def main() -> None:
    import os

    from .scrapy_runner import run

    run(SPIDER_NAME, OUTPUT_JSON, debug=bool(os.environ.get("DEBUG_SCRAPINGS", False)))


if __name__ == "__main__":
    from scrapy_runner import run

    run(SPIDER_NAME, OUTPUT_JSON, debug=True)

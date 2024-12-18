import json


def save_user_friendly_markdown(filename: str) -> None:
    with open(filename, "r", encoding="utf-8") as raw_json:
        data = json.load(raw_json)
        with open(f"{filename}.md", "w", encoding="utf-8") as md_file:
            for item in data:
                item_md = ["\n\n=============================="]
                item_md.append(f"{item['title']}, {item['url']}")
                if "main_content" in item:
                    item_md.append("\n------- @MAIN_CONTENT:\n")
                    item_md.append(item["main_content"])
                if "main_primary" in item:
                    item_md.append("\n------- @MAIN_PRIMARY:\n")
                    item_md.append(item["main_primary"])
                if "nonaccordion" in item:
                    item_md.append("\n------- @NONACCORDION:")
                    item_md.append(item["nonaccordion"])
                if "accordions" in item:
                    item_md.append("\n------- @ACCORDIONS:")
                    for heading, paras in item["accordions"].items():
                        item_md.append(f"\n---- ## {heading}:\n")
                        for para in paras:
                            item_md.append(para)
                md_file.write("\n".join(item_md))
            print("User-friendly markdown of JSON saved to %s.md", filename)


OUTPUT_JSON = "edd_scrapings.json"
SPIDER_NAME = "edd_spider"


def main() -> None:
    import os

    from .scrapy_runner import run

    debug = bool(os.environ.get("DEBUG_SCRAPINGS", False))
    run(SPIDER_NAME, OUTPUT_JSON, debug)

    if debug:
        save_user_friendly_markdown(OUTPUT_JSON)


if __name__ == "__main__":
    from scrapy_runner import run

    run(SPIDER_NAME, OUTPUT_JSON, debug=True)

import json
import re
from pathlib import Path
from typing import Iterator

import html2text
import scrapy
from scrapy.http import HtmlResponse, Response

PAGES_DIR = Path(__file__).resolve().parents[2] / "michigan_mdhhs" / "pages"
MAPPING_FILE = Path(__file__).resolve().parents[2] / "michigan_mdhhs" / "url_mapping.json"

# Elements to remove before markdown conversion (CSS selectors)
DROP_SELECTORS = [
    "section.section__pagefooter",
    "section.section__pagebreadcrumb",
    "section.section__pageheader",
    "div#browserDetectModal",
    "nav",
    "header",
    "footer",
    "script",
    "style",
    "noscript",
]


class MichiganMdhhsSpider(scrapy.Spider):
    name = "michigan_mdhhs_spider"

    # We read from local files, not from the network
    custom_settings = {
        "HTTPCACHE_ENABLED": False,
        "ROBOTSTXT_OBEY": False,
    }

    def start_requests(self) -> Iterator[scrapy.Request]:
        if not MAPPING_FILE.exists():
            self.logger.error(
                "URL mapping file not found at %s. Run scrape_michigan_mdhhs.py first.", MAPPING_FILE
            )
            return

        url_mapping: dict[str, str] = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
        self.logger.info("Loading %d pages from %s", len(url_mapping), PAGES_DIR)

        for filename, original_url in url_mapping.items():
            html_path = PAGES_DIR / filename
            if not html_path.exists():
                self.logger.warning("HTML file not found: %s", html_path)
                continue

            # Use file:// URL so Scrapy creates an HtmlResponse
            yield scrapy.Request(
                url=f"file://{html_path}",
                callback=self.parse_page,
                cb_kwargs={"original_url": original_url},
                dont_filter=True,
            )

    def parse_page(self, response: Response, original_url: str) -> dict[str, str]:
        assert isinstance(response, HtmlResponse)
        self.logger.info("Parsing %s", original_url)

        # Extract title from hero section or fallback to h1
        title = (
            response.css("div.hero-image__section-content-title h1::text").get()
            or response.css("h1::text").get()
            or ""
        ).strip()

        if not title:
            self.logger.warning("No title found for %s", original_url)
            title = original_url.rstrip("/").split("/")[-1].replace("-", " ").title()

        # Drop non-content elements
        for selector in DROP_SELECTORS:
            response.css(selector).drop()

        # Also drop sidebar navigation (keep only main content column)
        response.css("div.col-12.col-md-4").drop()

        # Extract main content — try multiple selectors
        main_html = (
            response.css("section#pagebody div.field-content").get()
            or response.css("section#pagebody div.col-12.col-md-8").get()
            or response.css("section#pagebody div.rte-content").get()
            or response.css("section#pagebody").get()
            or ""
        )

        if not main_html or len(main_html.strip()) < 50:
            self.logger.warning("Minimal content (%d chars) for %s", len(main_html.strip()), original_url)

        markdown = to_markdown(main_html, original_url)

        return {
            "url": original_url,
            "title": title,
            "markdown": markdown,
        }


def to_markdown(html: str | None, base_url: str | None = None) -> str:
    if not html:
        return ""

    h2t = html2text.HTML2Text()
    h2t.body_width = 0
    h2t.wrap_links = False
    h2t.include_sup_sub = False

    if base_url:
        h2t.baseurl = base_url

    markdown = h2t.handle(html.strip())

    # Consolidate multiple blank lines
    markdown = re.sub(r"\n\n+", "\n\n", markdown)
    return markdown.strip()

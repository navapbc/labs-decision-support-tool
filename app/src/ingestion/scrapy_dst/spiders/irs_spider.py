import re
from typing import Any, Callable, Iterable, Optional, Sequence

import html2text
from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector, SelectorList
from scrapy.spiders.crawl import CrawlSpider, Rule

from src.util import string_utils  # noqa: E402

AccordionSections = dict[str, list[str]]

"""
Use web browser to identify patterns across webpages (e.g., heading structure, common CSS classes) to do the scraping
Test scraping in the Scrapy shell: cd src/ingestion/; scrapy shell https://www.irs.gov/credits-deductions/family-dependents-and-students-credits
    # Grab the title for document.name
    title = response.css("h1.pup-page-node-type-article-page__title::text").get().strip()
    # Get element with non-boilerplate content
    pup = response.css("div.pup-main-container").get()
    # Remove elements to declutter desired content
    response.css("div.sidebar-left").drop()
    # Re-query after dropping
    pup = response.css("div.pup-main-container").get()
    # Convert to markdown
    import html2text
    h2t = html2text.HTML2Text()
    h2t.body_width = 0
    h2t.wrap_links = False
    # Check that it has all the desired content
    print(h2t.handle(pup))
Incorporate code into Scrapy spider
Run the spider:
    Set `CLOSESPIDER_ERRORCOUNT = 1` in app/src/ingestion/scrapy_dst/settings.py so that it stops on the first error
    Keep an eye on the cache in src/ingestion/.scrapy/httpcache/
    DEBUG_SCRAPINGS=true poetry run scrape-irs-web
Update spider with assertions and logger warnings to identify webpages that don't meet expectations
    Use `allow`, `deny`, and `restrict_css` to limit the crawl scope of the spider
Iterate

Examine irs_web_scrapings.json-pretty.json
Ingest: make ingest-irs-web DATASET_ID="IRS" BENEFIT_PROGRAM="tax credit" BENEFIT_REGION="US" FILEPATH=src/ingestion/irs_web_scrapings.json INGEST_ARGS="--skip_db"
Examine markdown files under irs_web_md/
"""


class IrsSpider(CrawlSpider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "irs_web_spider"
    allowed_domains = ["irs.gov"]
    start_urls = ["https://www.irs.gov/credits-deductions/family-dependents-and-students-credits"]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.irs.gov/"

    rules = (
        Rule(
            LinkExtractor(
                allow="www.irs.gov/credits-deductions/",
                deny=("www.irs.gov/credits-deductions/businesses"),
                allow_domains=allowed_domains,
                deny_domains=(),
                restrict_css=("div.pup-main-container"),
                canonicalize=True,
                unique=True,
            ),
            callback="parse_page",
            follow=True,
        ),
    )

    def parse_page(self, response: HtmlResponse) -> dict[str, str | AccordionSections]:
        self.logger.info("Parsing %s", response.url)
        extractions = {"url": response.url}

        if (h1_count := len(response.css("h1").getall())) > 1:
            self.logger.warning("Found %i h1 elements for %r", h1_count, response.url)
            raise ValueError("Multiple h1 elements found")

        if title_elem := response.css("h1.pup-page-node-type-article-page__title"):
            extractions["title"] = title_elem.css("::text").get().strip()
        elif title_elem := response.css("h1.pup-page-node-type-landing-page__title"):
            extractions["title"] = title_elem.css("::text").get().strip()
        else:
            self.logger.warning("No title for %r", response.url)
            raise ValueError("No title found")

        base_url = response.url
        if pup := response.css("div.pup-main-container"):
            # Remove elements to declutter desired content
            response.css("div.sidebar-left").drop()

            pup_html = pup.get()
            markdown = to_markdown(pup_html, base_url)
            extractions["markdown"] = markdown
        else:
            raise ValueError(f"No pup-main-container found in {response.url}")

        return extractions


def to_markdown(html: str, base_url: Optional[str] = None) -> str:
    h2t = html2text.HTML2Text()

    # Refer to https://github.com/Alir3z4/html2text/blob/master/docs/usage.md and html2text.config
    # for options:
    # 0 for no wrapping
    h2t.body_width = 0
    h2t.wrap_links = False

    if base_url:
        h2t.baseurl = base_url

    # Exclude the <sup> and <sub> tags
    h2t.include_sup_sub = False

    markdown = h2t.handle(html)

    # Consolidate newlines
    markdown = re.sub(r"\n\n+", "\n\n", markdown)
    return markdown.strip()

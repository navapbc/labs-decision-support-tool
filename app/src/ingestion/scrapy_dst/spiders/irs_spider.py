import re
from typing import Optional

import html2text
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders.crawl import CrawlSpider, Rule


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
                deny=(
                    "www.irs.gov/credits-deductions/businesses",
                    # These are about pandemic era changes to the child tax credit that aren't active anymore
                    # Exclude since they could be misleading if they get cited
                    r"2021-child-tax-credit-and-advance-child-tax-credit-payments.*",
                    r"tax-year-2021-filing-season-2022-child-tax-credit-frequently-asked-questions.*",
                    "advance-child-tax-credit-payments-in-2021/",
                    # Irrelavant pages
                    "clean-vehicle-and-energy-credits",
                ),
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

    def parse_page(self, response: HtmlResponse) -> dict[str, str]:
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

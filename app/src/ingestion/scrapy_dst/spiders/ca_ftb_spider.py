import re
from typing import Iterator, Optional

import html2text
import scrapy
from scrapy.http import HtmlResponse


class CaFranchiseTaxBoardSpider(scrapy.Spider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "ca_ftb_spider"
    allowed_domains = ["www.ftb.ca.gov"]
    start_urls = [
        "https://www.ftb.ca.gov/file/personal/credits/index.html",
        "https://www.ftb.ca.gov/about-ftb/newsroom/caleitc/eligibility-and-credit-information.html",
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.ftb.ca.gov/file/"

    def parse(self, response: HtmlResponse) -> Iterator[scrapy.Request | dict[str, str]]:
        self.logger.info("Parsing %s", response.url)

        # Only for the "Credit" page, follow the child pages
        if response.url == "https://www.ftb.ca.gov/file/personal/credits/index.html":
            nav_links = response.css("nav.local-nav a")
            for link in nav_links:
                if "class" in link.attrib and link.attrib["class"] == "uplevel":
                    # Skip the uplevel/back link that goes to the parent page
                    continue

                assert link.attrib["href"]
                self.logger.info("Found nav link: %s", link)
                yield response.follow(link, callback=self.parse_childpage)

        yield self.parse_childpage(response)

    def parse_childpage(self, response: HtmlResponse) -> dict[str, str]:
        self.logger.info("Parsing %s", response.url)

        if (h1_count := len(response.css("h1").getall())) > 1:
            self.logger.warning("Found %i h1 elements for %r", h1_count, response.url)
            raise ValueError("Multiple h1 elements found")

        title = to_markdown(response.css("h1").get().strip()).removeprefix("# ")
        assert title

        body = response.css("div#body-content")
        # Drop the navigation sidebar so that we only get the main content
        body.css("aside").drop()

        markdown = to_markdown(body.get(), response.url)
        assert markdown
        extractions = {
            "url": response.url,
            "title": title,
            "markdown": markdown,
        }
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

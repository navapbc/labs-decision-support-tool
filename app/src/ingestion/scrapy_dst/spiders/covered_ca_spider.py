import re
from typing import Iterator, Optional

import html2text
import scrapy
from scrapy.http import HtmlResponse


class CoveredCaliforniaSpider(scrapy.Spider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "covered_ca_spider"
    allowed_domains = ["www.coveredca.com"]
    start_urls = [
        "https://www.coveredca.com/support/before-you-buy/"
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.coveredca.com/"

    def parse(self, response: HtmlResponse) -> Iterator[scrapy.Request | dict[str, str]]:
        self.logger.info("Parsing %s", response.url)

        body = response.css("div.gtm-content")
        # h2content = primary.xpath("//h2/following-sibling::*[count(following-sibling::h2)=1]")
        for item in body.css("h2, a"):
            if item.root.tag == "h2":
                topic = to_markdown(item.get().strip()).removeprefix("## ")
                self.logger.info("Topic: %r", topic)
            elif item.root.tag == "a":
                assert item.attrib["href"]
                self.logger.info("  Found link: %s", item)
                yield response.follow(item, callback=self.parse_childpage, cb_kwargs={"topic": topic})
            else:
                raise ValueError(f"Unexpected tag {item.root.tag}")

        yield self.parse_childpage(response)

    def parse_childpage(self, response: HtmlResponse, topic: Optional[str] = None) -> dict[str, str]:
        self.logger.info("Parsing %s with %r", response.url, topic)

        if (h1_count := len(response.css("h1").getall())) > 1:
            self.logger.warning("Found %i h1 elements for %r", h1_count, response.url)
            raise ValueError("Multiple h1 elements found")

        title = to_markdown(response.css("h1").get().strip()).removeprefix("# ").strip()
        assert title
        title = f"{topic}: {title}" if topic else title

        body = response.css("div.gtm-content")
        if not body:
            body = response.css("div[data-cms-source]")
        markdown = to_markdown(body.get(), response.url)
        assert markdown
        extractions = {
            "url": response.url,
            "title": title,
            "markdown": markdown,
        }
        return extractions


def to_markdown(html: str, base_url: Optional[str] = None) -> str:
    assert html
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

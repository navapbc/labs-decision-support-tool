import re
from typing import Optional

import html2text
import scrapy
from scrapy.http import HtmlResponse


class CaWicSpider(scrapy.Spider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "ca_wic_spider"
    allowed_domains = ["www.phfewic.org"]
    start_urls = [
        "https://www.phfewic.org/en/how-wic-works/apply-for-wic/",
        "https://www.phfewic.org/en/how-wic-works/faqs/",
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.phfewic.org/en/"

    def parse(self, response: HtmlResponse) -> dict[str, str]:
        self.logger.info("Parsing %s", response.url)

        if (h1_count := len(response.css("h1").getall())) > 1:
            self.logger.warning("Found %i h1 elements for %r", h1_count, response.url)
            raise ValueError("Multiple h1 elements found")

        title = to_markdown(response.css("h1").get().strip()).removeprefix("# ")
        assert title

        markdowns = []
        header = response.css("div#page-no-header")
        if header:
            markdowns.append(to_markdown(header.get(), response.url))

        body = response.css("div#content")
        markdowns.append(to_markdown(body.get(), response.url))
        assert markdowns
        extractions = {
            "url": response.url,
            "title": title,
            "markdown": "\n\n".join(markdowns),
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

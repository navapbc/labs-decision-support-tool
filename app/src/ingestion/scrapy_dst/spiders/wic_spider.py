from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import SelectorList
from scrapy.spiders.crawl import CrawlSpider, Rule

from src.util import string_utils  # noqa: E402

AccordionSections = dict[str, list[str]]


class WicSpider(CrawlSpider):
    # This name is used on the commandline: scrapy crawl wic_spider
    name = "wic_spider"
    allowed_domains = ["www.phfewic.org"]
    start_urls = [
        "https://www.phfewic.org/en/how-wic-works/apply-for-wic/"
        "https://www.phfewic.org/en/how-wic-works/faqs/"
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "www.phfewic.org"

    rules = (
        Rule(
            LinkExtractor(
                allow=r"en",
                deny=(),
                # allow_domains=allowed_domains,
                deny_domains=(),
                canonicalize=True,
                unique=True,
            ),
            callback="parse_page",
            follow=True,
        ),
    )

    def parse_page(self, response: HtmlResponse) -> dict[str, str | AccordionSections]:
        extractions = {"url": response.url}
        if len(response.css("h1::text").getall()) == 1:
            title = response.css("h1::text").get()
            extractions["title"] = title.strip()
        base_url = response.url
        print("URL:", base_url)
        extractions |= self.parse_main_primary(base_url, response.css("div.col-lg-6 contact-right"))
        # extractions |= self.parse_main_content(base_url, response.css("div.GTM-1"))

        return extractions

    def to_markdown(self, base_url: str, html: str) -> str:

        markdown = markdownify(
            html,
            heading_style="ATX",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
            sup_symbol="<sup>",
            sub_symbol="<sub>",
        )

        markdown = string_utils.resolve_urls(base_url, markdown)
        return markdown.strip()

    def parse_main_primary(self, base_url: str, main_primary: SelectorList) -> dict[str, str]:
        markdown = self.to_markdown(base_url, main_primary.get())
        return {"main_primary": markdown}

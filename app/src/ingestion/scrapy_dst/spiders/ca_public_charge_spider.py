import re

from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import SelectorList
from scrapy.spiders.crawl import CrawlSpider, Rule

from src.util import string_utils  # noqa: E402

AccordionSections = dict[str, list[str]]


class CaPublicChargeSpider(CrawlSpider):
    # This name is used on the commandline: scrapy crawl ca_public_charge_spider
    name = "ca_public_charge_spider"
    allowed_domains = ["keepyourbenefits.org"]
    start_urls = ["https://keepyourbenefits.org/en/ca/public-charge"]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://keepyourbenefits.org/en/ca/"

    rules = (
        Rule(
            LinkExtractor(
                allow=r"en/ca",
                deny=(
                    "es/ca/public-charge",  # has non-English content
                    "media/",
                    "_ima/",
                    "use-the-guide",
                    "find-help",
                ),
                allow_domains=allowed_domains,
                deny_domains=("https://s3.amazonaws.com",),
                canonicalize=True,
                unique=True,
            ),
            callback="parse_page",
            follow=True,
        ),
    )

    def parse_page(self, response: HtmlResponse) -> dict[str, str | AccordionSections]:
        extractions = {"url": response.url}
        title = response.css("title::text").get().split("| Keep Your Benefits", 1)[0]
        extractions["title"] = title.strip()
        base_url = response.url

        # remove icon text
        response.css("div.ic-icon").drop()

        extractions |= self.parse_main_primary(base_url, response.css("div.module-full"))
        extractions |= self.parse_main_content(base_url, response.css("div.GTM-1"))

        return extractions

    def to_markdown(self, base_url: str, html: str) -> str:
        # convert larger text to header
        larger_font_pattern = (
            r'<p class="title fontsize-30 weightier colored text-center"([^>]*?)>(.*?)<\/p>'
        )
        html = re.sub(larger_font_pattern, r"<h3\1>\2</h3>", html)

        markdown = markdownify(
            html,
            heading_style="ATX",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
            sup_symbol="<sup>",
            sub_symbol="<sub>",
            strip=["img", "i"],
        )

        # Clean up markdown text: consolidate newlines; replace non-breaking spaces; replace unicode char with dash,
        markdown = (
            re.sub(r"\n\n+", "\n\n", markdown).replace("\u00A0", " ").replace("\n\u2022", "-")
        )
        # Replace non-absolute URLs with absolute URLs
        markdown = string_utils.resolve_urls(base_url, markdown)
        return markdown.strip()

    def parse_main_primary(self, base_url: str, main_primary: SelectorList) -> dict[str, str]:
        markdown = self.to_markdown(base_url, main_primary.get())
        return {"main_primary": markdown}

    def parse_main_content(self, base_url: str, main_content: SelectorList) -> dict[str, str]:
        markdown = ""
        two_column_details = main_content.css("div.list-twocolumn").getall()
        # first middler element is state selection dropdown item
        middler_details = main_content.css("div.middler").getall()[1:]

        if two_column_details:
            for one_column in two_column_details:
                markdown += "\n" + self.to_markdown(base_url, one_column)
        if middler_details:
            for middle_detail in middler_details:
                markdown += "\n" + self.to_markdown(base_url, middle_detail)

        return {"main_content": markdown}

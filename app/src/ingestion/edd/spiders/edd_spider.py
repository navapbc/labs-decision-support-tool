# import scrapy
# from w3lib.html import remove_tags
import re

from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector, SelectorList
from scrapy.spiders.crawl import CrawlSpider, Rule

AccordionSections = dict[str, list[str]]


class EddSpider(CrawlSpider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "edd_spider"
    allowed_domains = ["edd.ca.gov"]
    start_urls = ["https://edd.ca.gov/en/claims"]

    rules = (
        Rule(
            LinkExtractor(
                allow=r"en/",
                deny=(
                    # "en/language-resources" has non-English content
                    "en/language-resources",
                    # "EPiServer/CMS/Content" links to CMS backend content
                    "EPiServer/CMS/Content",
                    # "/archived-news-releases-..." redirects to pdf files
                    "/archived-news-releases",
                ),
                allow_domains=allowed_domains,
                deny_domains=(
                    # Avoid crawling CMS backend content
                    "cms.edd.ca.gov",
                    # Avoid crawling EDD services like https://eddservices.edd.ca.gov/tap/open/rateinquiry
                    "eddservices.edd.ca.gov",
                ),
                restrict_css=("div.two-thirds", "main.main-primary"),
            ),
            callback="parse_page",
            follow=True,
        ),
    )

    def parse_page(self, response: HtmlResponse) -> dict[str, str | AccordionSections]:
        extractions = {"url": response.url}

        title = response.css("div.full-width-title h1::text").get()
        if len(response.css("h1::text").getall()) == 1:
            title = response.css("h1::text").get()
            extractions["title"] = title
        else:
            titles = ";".join(response.css("h1::text").getall())
            extractions["title"] = titles

        if main_content := response.css("div.two-thirds"):
            # Remove buttons from the main content, i.e., "Show All"
            main_content.css("button").drop()
            extractions |= self.parse_entire_two_thirds(main_content)

            if main_content.css("div.panel-group.accordion"):
                # If these parse methods become more complicated, move them to items.py
                # and use ItemLoaders https://docs.scrapy.org/en/latest/topics/loaders.html
                extractions |= self.parse_nonaccordion(main_content)
                extractions |= self.parse_accordions(main_content)
        elif main_primary := response.css("main.main-primary"):
            main_primary.css("button").drop()
            extractions |= self.parse_main_primary(main_primary)
        else:
            pass

        return extractions

    def to_markdown(self, html: str) -> str:
        markdown = markdownify(
            html,
            heading_style="ATX",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
            sup_symbol="<sup>",
            sub_symbol="<sub>",
        )
        # Clean up markdown text: consolidate newlines; replace non-breaking spaces
        markdown = re.sub(r"\n\n+", "\n\n", markdown).replace("\u00A0", " ")
        return markdown.strip()

    def parse_main_primary(self, main_primary: SelectorList) -> dict[str, str]:
        markdown = self.to_markdown(main_primary.get())
        return {"main_primary": markdown}

    def parse_entire_two_thirds(self, main_content: SelectorList) -> dict[str, str]:
        markdown = self.to_markdown(main_content.get())
        cleaned_markdown = re.sub(r"\[(.*?)\]\(#collapse-(.*?)\)", r"\1", markdown)
        return {"main_content": cleaned_markdown}

    def parse_nonaccordion(self, main_content: SelectorList) -> dict[str, str]:
        # Create a copy for modification without affecting the original
        nonaccordion = Selector(text=main_content.get())
        nonaccordion.css("div.panel-group.accordion").drop()
        return {"nonaccordion": self.to_markdown(nonaccordion.get())}

    def parse_accordions(self, main_content: SelectorList) -> dict[str, AccordionSections]:
        sections: AccordionSections = {}
        for p in main_content.css("div.panel.panel-default"):
            heading = p.css("div.panel-heading :is(h2, h3, h4, h5, h6) a::text").get().strip()
            paragraphs = p.css("div.panel-body")
            sections[heading] = [self.to_markdown(para.get()) for para in paragraphs]

        return {"accordions": sections}

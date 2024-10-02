# import scrapy
# from w3lib.html import remove_tags
import re
from markdownify import markdownify
from scrapy.selector import Selector
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor


class EddSpiderSpider(CrawlSpider):
    name = "edd_spider"
    allowed_domains = ["edd.ca.gov"]
    start_urls = [
        "https://edd.ca.gov/en/disability/About_the_State_Disability_Insurance_SDI_Program",
        #     "https://edd.ca.gov/en/Disability/Am_I_Eligible_for_DI_Benefits",
        "https://edd.ca.gov/en/disability/how_to_file_a_di_claim_by_mail",
    ]

    rules = (Rule(LinkExtractor(allow=r"en/"), callback="parse_item"),)

    def parse(self, response):
        pass

    def parse_item(self, response):
        title = response.css("div.full-width-title h1::text").get()
        assert len(response.css("h1::text").getall()) == 1
        assert title == response.css("h1::text").get()

        main_content = response.css("div.two-thirds")
        # Remove buttons from the main content, i.e., "Show All"
        main_content.css("button").drop()

        extractions = {"url": response.url, "title": title} | self.parse_entire_two_thirds(
            main_content
        )
        if main_content.css("div.panel-group.accordion"):
            extractions |= self.parse_nonaccordion(main_content)
            extractions |= self.parse_accordions(main_content)
        return extractions

    def to_markdown(self, html):
        markdown = markdownify(
            html,
            heading_style="ATX",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
            sup_symbol="<sup>",
            sub_symbol="<sub>",
        )
        # Clean up markdown text: consolidate newlines, remove escaped hyphens
        markdown = re.sub(r"\n\n+", "\n\n", markdown)
        return markdown.strip()

    def parse_entire_two_thirds(self, main_content):
        markdown = self.to_markdown(main_content.get())
        cleaned_markdown = re.sub(r"\[(.*?)\]\(#collapse-(.*?)\)", r"\1", markdown)
        return {"main_content": cleaned_markdown}

    def parse_nonaccordion(self, main_content):
        # Create a copy so we can call drop() on it
        nonaccordion = Selector(text=main_content.get())
        nonaccordion.css("div.panel-group.accordion").drop()
        return {"nonaccordion": self.to_markdown(nonaccordion.get())}

    def parse_accordions(self, main_content):
        panels = main_content.css("div.panel.panel-default")
        if not panels:
            return {}

        sections: dict[str, list[str]] = {}
        for p in panels:
            heading = p.css("div.panel-heading :is(h2, h3, h4, h5, h6) a::text").get().strip()
            paragraphs = p.css("div.panel-body")
            sections[heading] = [self.to_markdown(para.get()) for para in paragraphs]

        return {"accordions": sections}

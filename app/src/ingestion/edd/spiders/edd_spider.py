# import scrapy
# from w3lib.html import remove_tags
import re

from markdownify import markdownify
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector
from scrapy.spiders.crawl import CrawlSpider, Rule


class EddSpider(CrawlSpider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "edd_spider"
    allowed_domains = ["edd.ca.gov"]
    start_urls = [
        "https://edd.ca.gov/en/disability/About_the_State_Disability_Insurance_SDI_Program",
        #     "https://edd.ca.gov/en/Disability/Am_I_Eligible_for_DI_Benefits",
        "https://edd.ca.gov/en/disability/how_to_file_a_di_claim_by_mail",
        "https://edd.ca.gov/en/disability/Faqs/",
    ]

    rules = (Rule(LinkExtractor(allow=r"en/"), callback="parse_page"),)

    def parse(self, response):
        pass

    def parse_page(self, response):
        title = response.css("div.full-width-title h1::text").get()
        assert len(response.css("h1::text").getall()) == 1
        assert title == response.css("h1::text").get()
        extractions = {"url": response.url, "title": title}

        if main_content := response.css("div.two-thirds"):
            # Remove buttons from the main content, i.e., "Show All"
            main_content.css("button").drop()
            extractions |= self.parse_entire_two_thirds(main_content)

            if main_content.css("div.panel-group.accordion"):
                extractions |= self.parse_nonaccordion(main_content)
                extractions |= self.parse_accordions(main_content)
        elif main_primary := response.css("main.main-primary"):
            extractions |= self.parse_main_primary(main_primary)
        else:
            pass

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
        # Clean up markdown text: consolidate newlines; replace non-breaking spaces
        markdown = re.sub(r"\n\n+", "\n\n", markdown).replace("\u00A0", " ")
        return markdown.strip()

    def parse_main_primary(self, main_primary):
        markdown = self.to_markdown(main_primary.get())
        return {"main_primary": markdown}

    def parse_entire_two_thirds(self, main_content):
        markdown = self.to_markdown(main_content.get())
        cleaned_markdown = re.sub(r"\[(.*?)\]\(#collapse-(.*?)\)", r"\1", markdown)
        return {"main_content": cleaned_markdown}

    def parse_nonaccordion(self, main_content):
        # Create a copy for modification without affecting the original
        nonaccordion = Selector(text=main_content.get())
        nonaccordion.css("div.panel-group.accordion").drop()
        return {"nonaccordion": self.to_markdown(nonaccordion.get())}

    def parse_accordions(self, main_content):
        sections: dict[str, list[str]] = {}
        panels = main_content.css("div.panel.panel-default")
        for p in panels:
            heading = p.css("div.panel-heading :is(h2, h3, h4, h5, h6) a::text").get().strip()
            paragraphs = p.css("div.panel-body")
            sections[heading] = [self.to_markdown(para.get()) for para in paragraphs]

        return {"accordions": sections}

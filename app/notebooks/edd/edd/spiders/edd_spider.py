# import scrapy
# from w3lib.html import remove_tags
import re
from markdownify import markdownify
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor


class EddSpiderSpider(CrawlSpider):
    name = "edd_spider"
    allowed_domains = ["edd.ca.gov"]
    start_urls = [
        "https://edd.ca.gov/en/disability/About_the_State_Disability_Insurance_SDI_Program",
        #     "https://edd.ca.gov/en/Disability/Am_I_Eligible_for_DI_Benefits",
        #     "https://edd.ca.gov/en/disability/how_to_file_a_di_claim_by_mail"
    ]

    rules = (Rule(LinkExtractor(allow=r"en/"), callback="parse_item"),)

    def parse(self, response):
        pass

    def parse_item(self, response):
        print("parse_item", response.url)

        title = response.css("div.full-width-title h1::text").get()
        assert len(response.css("h1::text").getall()) == 1
        assert title == response.css("h1::text").get()

        return (
            {"url": response.url, "title": title}
            | self.parse_two_thirds(response)
            | self.parse_accordion(response)
        )


    def to_markdown(self, html):
        markdown = markdownify(html, heading_style="ATX")
        # Clean up markdown text: consolidate newlines, remove escaped hyphens
        markdown = re.sub(r'\n\n+', '\n\n', markdown)
        return markdown.replace("\\-", "-").strip()

    def parse_two_thirds(self, response):
        main_content = response.css("div.two-thirds")
        return {"main_content": self.to_markdown(main_content.get())}

    def parse_accordion(self, response):

        # main_content = response.css("div.two-thirds")
        # headings = main_content.css("h2").getall()
        panels = response.css("div.panel.panel-default")
        if not panels:
            return {}

        h2sections: dict[str, list[str]] = {}
        for p in panels:
            heading = p.css("div.panel-heading h2 a::text").get()
            paragraphs = p.css("div.panel-body")
            h2sections[heading] = [
                self.to_markdown(para.get()) for para in paragraphs
            ]

        return {"h2sections": h2sections}

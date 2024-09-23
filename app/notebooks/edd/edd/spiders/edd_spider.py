import scrapy
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

    rules = (
        Rule(LinkExtractor(allow=r"en/"), callback="parse_item"),
    )

    def parse(self, response):
        pass

    def parse_item(self, response):
        print("parse_item", response.url)
        item = {}
        return item

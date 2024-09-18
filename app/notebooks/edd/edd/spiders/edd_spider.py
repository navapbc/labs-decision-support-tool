import scrapy
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

class EddSpiderSpider(CrawlSpider):
    name = "edd_spider"
    allowed_domains = ["edd.ca.gov"]
    start_urls = ["https://edd.ca.gov/en/File_and_Manage_a_Claim"]

    rules = (
        Rule(LinkExtractor(allow=r"en/"), callback="parse_item"),
    )

    def parse(self, response):
        pass

    def parse_item(self, response):
        print("parse_item", response.url)
        item = {}
        return item
import re
from typing import Iterator, Optional

import html2text
import scrapy
from scrapy.http import HtmlResponse
from scrapy.selector import Selector


class CoveredCaliforniaSpider(scrapy.Spider):
    # This name is used on the commandline: scrapy crawl edd_spider
    name = "covered_ca_spider"
    allowed_domains = ["www.coveredca.com"]
    start_urls = [
        "https://www.coveredca.com/support/before-you-buy/",
        "https://www.coveredca.com/support/getting-started/",
        "https://www.coveredca.com/support/financial-help/",
        "https://www.coveredca.com/support/account/",
        "https://www.coveredca.com/support/using-my-plan/",
        "https://www.coveredca.com/support/membership/",
        # Glossary layout
        "https://www.coveredca.com/support/glossary/",
        # Different layout
        "https://www.coveredca.com/learning-center/information-for-immigrants/",
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.coveredca.com/"

    def parse(self, response: HtmlResponse) -> Iterator[scrapy.Request | dict[str, str]]:
        self.logger.info("Parsing %s", response.url)
        if response.url == "https://www.coveredca.com/support/glossary/":
            yield self.parse_glossary(response)
        elif (
            response.url == "https://www.coveredca.com/learning-center/information-for-immigrants/"
        ):
            row_cols = response.css("div#content div.container > div.row > div.col-12")
            assert len(row_cols) == 2
            for col in row_cols:
                if "sidebar" in col.root.attrib["class"]:
                    for link in col.css("div.sidebar__body a"):
                        assert link.attrib["href"]
                        self.logger.info("Found sidebar link: %s", link)
                        yield response.follow(link, callback=self.parse_learning_center_page)
                else:
                    extractions = self.parse_learning_center_body(response.url, col)
                    yield extractions
        else:
            body = response.css("div.gtm-content")
            # h2content = primary.xpath("//h2/following-sibling::*[count(following-sibling::h2)=1]")
            topic = None
            for item in body.css("h2, a"):
                if item.root.tag == "h2":
                    topic = to_markdown(item.get().strip()).removeprefix("## ")
                    self.logger.info("Topic: %r", topic)
                elif item.root.tag == "a":
                    assert item.attrib["href"]
                    self.logger.info("  Found link: %s", item)
                    yield response.follow(
                        item, callback=self.parse_support_page, cb_kwargs={"topic": topic}
                    )
                else:
                    raise ValueError(f"Unexpected tag {item.root.tag}")

            yield self.parse_support_page(response)

    def parse_learning_center_page(
        self, response: HtmlResponse
    ) -> Iterator[scrapy.Request | dict[str, str]]:
        self.logger.info("Parsing under Learning Center: %s ", response.url)
        row_cols = response.css("div#content div.container > div.row > div.col-12")
        assert len(row_cols) == 2
        for col in row_cols:
            if "sidebar" in col.root.attrib["class"]:
                # Skip the sidebar since it was already processed
                continue
            else:
                extractions = self.parse_learning_center_body(response.url, col)
                yield extractions

    def parse_learning_center_body(self, url: str, col: Selector) -> dict[str, str]:
        title = to_markdown(col.css("h1").get().strip()).removeprefix("# ").strip()
        assert title
        markdown = to_markdown(col.get(), url)
        assert markdown
        extractions = {
            "url": url,
            "title": title,
            "markdown": markdown,
        }
        return extractions

    def parse_support_page(
        self, response: HtmlResponse, topic: Optional[str] = None
    ) -> dict[str, str]:
        self.logger.info("Parsing under topic %r: %s ", topic, response.url)

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
            "markdown": f"# {title}\n\n{markdown}",
        }
        return extractions

    def parse_glossary(self, response: HtmlResponse, topic: Optional[str] = None) -> dict[str, str]:
        self.logger.info("Parsing glossary: %s ", response.url)

        title = "Glossary"
        markdowns = [f"# {title}"]

        body = response.css("div#main-content-container_primary section + div.container")
        assert len(body) == 1
        def_lists = body.css("dl")
        for dl in def_lists:
            for d_tag in dl.css("dt, dd"):
                if d_tag.root.tag == "dt":
                    if term := to_markdown(d_tag.get()).strip():
                        markdowns.append(f"## {term}")
                elif d_tag.root.tag == "dd":
                    if dd := to_markdown(d_tag.get()).strip():
                        if not term:
                            self.logger.warning("Empty term for definition: %r", dd)
                        markdowns.append(dd)
                else:
                    raise ValueError(f"Unexpected tag {d_tag.root.tag}")

        self.logger.info("Glossary has %i terms", (len(markdowns) - 1) / 2)
        extractions = {
            "url": response.url,
            "title": title,
            "markdown": "\n\n".join(markdowns),
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

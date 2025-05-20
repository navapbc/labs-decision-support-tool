import re
from typing import Iterator, Optional

import html2text
import scrapy
from scrapy.http import HtmlResponse, Response
from scrapy.selector import Selector


class CoveredCaliforniaSpider(scrapy.Spider):
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
        # Different layout - grid boxes
        "https://www.coveredca.com/documents-to-confirm-eligibility/",
    ]

    # This is used to substitute the base URL in the cache storage
    common_url_prefix = "https://www.coveredca.com/"

    def parse(self, response: Response) -> Iterator[scrapy.Request | dict[str, str]]:
        assert isinstance(response, HtmlResponse)
        return self.parse_html(response)

    def parse_html(self, response: HtmlResponse) -> Iterator[scrapy.Request | dict[str, str]]:
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
                    assert isinstance(col, Selector)
                    yield self.parse_learning_center_body(response.url, col)
        elif response.url.startswith("https://www.coveredca.com/support/"):
            body = response.css("div.gtm-content")
            topic = None
            for item in body.css("h2, a"):
                if item.root.tag == "h2":
                    topic = to_markdown(item.get()).removeprefix("## ")
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
        elif response.url == "https://www.coveredca.com/documents-to-confirm-eligibility/":
            title = to_markdown(response.css("h1").get()).removeprefix("# ")
            assert title
            markdown = to_markdown(response.css("#content").get(), response.url)
            assert markdown
            extractions = {
                "url": response.url,
                "title": title,
                "markdown": markdown,
            }
            yield extractions

            # Extract links to subpages
            primary_section = response.css("section.bg-primary")
            assert len(primary_section) == 1
            for href in primary_section.css("a::attr(href)").getall():
                assert href
                self.logger.info("Found link: %s", href)
                yield response.follow(href, callback=self.parse_eligibility_doc_page)
        else:
            raise ValueError(f"Unexpected URL: {response.url}")

    def parse_learning_center_page(
        self, response: Response
    ) -> Iterator[scrapy.Request | dict[str, str]]:
        assert isinstance(response, HtmlResponse)
        self.logger.info("Parsing under Learning Center: %s ", response.url)
        row_cols = response.css("div#content div.container > div.row > div.col-12")
        assert len(row_cols) == 2
        for col in row_cols:
            if "sidebar" in col.root.attrib["class"]:
                # Skip the sidebar since it was already processed
                continue
            else:
                assert isinstance(col, Selector)
                extractions = self.parse_learning_center_body(response.url, col)
                yield extractions

    def parse_learning_center_body(self, url: str, col: Selector) -> dict[str, str]:
        title = to_markdown(col.css("h1").get()).removeprefix("# ").strip()
        assert title
        markdown = to_markdown(col.get(), url)
        assert markdown
        extractions = {
            "url": url,
            "title": title,
            "markdown": markdown,
        }
        return extractions

    def parse_support_page(self, response: Response, topic: Optional[str] = None) -> dict[str, str]:
        assert isinstance(response, HtmlResponse)
        self.logger.info("Parsing under topic %r: %s ", topic, response.url)

        if (h1_count := len(response.css("h1").getall())) > 1:
            self.logger.warning("Found %i h1 elements for %r", h1_count, response.url)
            raise ValueError("Multiple h1 elements found")

        title = to_markdown(response.css("h1").get()).removeprefix("# ").strip()
        assert title
        title = f"{topic}: {title}" if topic else title

        body_sel = response.css("div.gtm-content")
        if not body_sel:
            body_sel = response.css("div[data-cms-source]")

        markdowns = []
        for body in body_sel:
            md = to_markdown(body.get(), response.url)
            assert md
            if body.css("table"):
                self.logger.warning("Ignored table formatting for: %r", md)
            markdowns.append(md)
        markdown = "\n\n".join(markdowns)
        return {
            "url": response.url,
            "title": title,
            "markdown": f"# {title}\n\n{markdown}",
        }

    def parse_glossary(self, response: Response, topic: Optional[str] = None) -> dict[str, str]:
        assert isinstance(response, HtmlResponse)
        self.logger.info("Parsing glossary: %s ", response.url)

        title = "Glossary"
        markdowns = [f"# {title}"]

        body = response.css("div#main-content-container_primary section + div.container")
        assert len(body) == 1
        def_lists = body.css("dl")
        for dl in def_lists:
            for d_tag in dl.css("dt, dd"):
                if d_tag.root.tag == "dt":
                    if term := to_markdown(d_tag.get()):
                        markdowns.append(f"## {term}")
                elif d_tag.root.tag == "dd":
                    if dd := to_markdown(d_tag.get()):
                        if not term:
                            self.logger.warning("Empty term for definition: %r", dd)
                        markdowns.append(dd)
                else:
                    raise ValueError(f"Unexpected tag {d_tag.root.tag}")

        self.logger.info("Glossary has %i terms", (len(markdowns) - 1) / 2)
        return {
            "url": response.url,
            "title": title,
            "markdown": "\n\n".join(markdowns),
        }

    def parse_eligibility_doc_page(self, response: Response) -> dict[str, str]:
        assert isinstance(response, HtmlResponse)
        # These pages can be parsed like support pages
        return self.parse_support_page(response)


def to_markdown(html: Optional[str], base_url: Optional[str] = None) -> str:
    if not html:
        return ""

    h2t = html2text.HTML2Text()

    # Refer to https://github.com/Alir3z4/html2text/blob/master/docs/usage.md and html2text.config
    # for options:
    # 0 for no wrapping
    h2t.body_width = 0
    h2t.wrap_links = False

    # Page https://www.coveredca.com/support/before-you-buy/copays-deductibles-coinsurance/
    # (unintentionally?) wrapped the main text in a single-cell table,
    # which results in markdown with text followed by `---`, which causes the text to be interpreted as heading
    h2t.ignore_tables = True

    if base_url:
        h2t.baseurl = base_url

    # Exclude the <sup> and <sub> tags
    h2t.include_sup_sub = False

    markdown = h2t.handle(html.strip())

    # Consolidate newlines
    markdown = re.sub(r"\n\n+", "\n\n", markdown)
    return markdown.strip()

import pdb
import logging
import os
import re
import sys

from pathlib import Path
from markdownify import markdownify

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

import scrapy
from scrapy.http import HtmlResponse
from scrapy.selector import Selector, SelectorList

app_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
print("Adding app folder to sys.path:", app_folder)
sys.path.append(app_folder)
from src.util import string_utils  # noqa: E402

logger = logging.getLogger(__name__)


class LA_PolicyManualSpider(scrapy.Spider):
    name = "la_policy_spider"

    # TODO: Port playwrite code to scrapy via https://github.com/scrapy-plugins/scrapy-playwright?tab=readme-ov-file#executing-actions-on-pages
    start_urls = [
        "file:////Users/yoom/dev/labs-decision-support-tool/app/src/ingestion/imagine_la/scrape/pagesT1/expanded_all_programs.html"
    ]

    # def start_requests(self):
    #     urls = [
    #         "file:////Users/yoom/dev/labs-decision-support-tool/app/src/ingestion/imagine_la/scrape/pagesT1/expanded_all_programs.html"
    #     ]
    #     for url in urls:
    #         yield scrapy.Request(url=url, callback=self.parse)

    common_url_prefix = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster"

    def parse(self, response: HtmlResponse):
        page = response.url.split("/")[-1]
        filename = f"page-{page}.html"
        Path(filename).write_bytes(response.body)
        self.log(f"Saved file {filename}")

        lis = response.css("li.book")
        for li in lis[2:]:  # Start with "Programs" li
            print(li)
            href = li.css("a::attr(href)").get()
            if href != "#":
                page_url = f"{self.common_url_prefix}/{href}"
                print("Page URL", page_url)
                yield response.follow(page_url, callback=self.parse_page)
                break

    def parse_page(self, response: HtmlResponse):
        print("parse_page", response.url.split())

        Path(f"{response.url.split("/")[-1]}").write_bytes(response.body)
        Path(f"{response.url.split("/")[-1]}_0.md").write_text(to_markdown(self.common_url_prefix, response.text))

        tables = response.xpath("body/table")
        assert len(tables)==1, "Expected one top-level table"
        rows = response.xpath("body/table/tr")

        base_url = self.common_url_prefix
        header_md = to_markdown(base_url, rows[0].get())
        assert "Release Date" in header_md, "Expected 'Release Date' in first row (which acts as page header)"

        markdown: list[str] = []
        for row in rows[1:]:
            tds = row.xpath("./td")
            if len(tds) == 1:
                p = tds[0].xpath("./p")
                p_class = p.attrib['class']
                if p_class == "WD_ProgramName":
                    heading_md = "# " + to_markdown(base_url, self._parse_heading(p))
                elif p_class == "WD_SubjectLine":
                    heading_md = "## " + to_markdown(base_url, self._parse_heading(p))
                else:
                    heading_md = "###? " + to_markdown(base_url, self._parse_heading(tds[0]))
                    print("Heading row", heading_md)
                    pdb.set_trace()
                markdown.append(heading_md)
            elif len(tds) == 2:
                heading_md = "### " + to_markdown(base_url, self._parse_heading(tds[0]))
                print("HeadingSection row", heading_md)
                section_md = self._parse_section(base_url, tds[1])
                markdown.append("\n\n".join([heading_md, section_md]))
            else:
                raise NotImplementedError(f"Unexpected number of columns in row: {len(tds)}: {row.get()}")
                pdb.set_trace()
        Path(f"{response.url.split("/")[-1]}.md").write_text("\n\n".join(markdown))

    def _parse_heading(self, cell: Selector) -> str:
        raw_texts = cell.xpath('.//text()').getall()
        return "".join(raw_texts)
    
    def _parse_section(self, base_url, section: Selector) -> str:
        # section_md = to_markdown(base_url, "\n\n".join(section.xpath('.//text()').getall()))
        # test_section = _test_selector()
        # bs = _test_bs()
        # for child in bs.children:
        #     print(child)
        #     if isinstance(child, NavigableString):
        #         child.get_text()
        # childs = test_section.xpath('//td/* or text()')

        soup = BeautifulSoup(section.get(), 'html.parser')
        body = soup.find("td")
        body.name="div"
        current_list = None
        for child in body.children:
            if child.name == "p":
                if "WD_ListParagraphCxSpFirst" in child['class']:
                    current_list = soup.new_tag("ul")
                if any(c in ["WD_ListParagraphCxSpFirst", "WD_ListParagraphCxSpMiddle", "WD_ListParagraphCxSpLast"] for c in child['class']):
                    child.name = "li"
                    child.wrap(current_list)

                    list_body = list(child.children)
                    [c for c in child.children]
                    if list_body[0].name == "span" and list_body[0].get_text() == "·\xa0\xa0\xa0\xa0\xa0\xa0\xa0":
                        # Remove the bullet point
                        list_body[0].decompose()
                    else:
                        pdb.set_trace()

                    if list_body[1].get_text() == " ":
                        # Remove space after bullet point
                        list_body[1].extract()
                    else:
                        pdb.set_trace()

                    if list_body[2].name == "span" and list_body[2]["dir"] == "ltr" and list_body[2].get_text() == "":
                        # Remove "left-to-right" span -- not sure what this is for
                        list_body[2].decompose()
                    else:
                        pdb.set_trace()

                    # if any(c not in [None, "br"] for c in child.children):
                    #     print([c.name for c in child.children])
                    #     pdb.set_trace()
                    for c in child.children:
                        if c.name == "br":
                            pass # c.decompose()
                        elif isinstance(c, NavigableString):
                            c.replace_with(c.string.strip())
                        else:
                            pdb.set_trace()

                    # pdb.set_trace()

        new_html = str(soup)
        section_md = to_markdown(base_url, new_html)
        section_md = re.sub(r"\n\n \n\n", "\n\n", section_md)
        # print(section_md)
        # lis = soup.select("div > ul > li")
        # pdb.set_trace()
        return section_md


test_html = """
<td width=123>
    intro
    <p>paragraph 1</p>
    <p>paragraph 2</p>
</td>
"""

def _test_selector():
    return Selector(text=test_html)

def _test_bs():
    return BeautifulSoup(test_html, 'html.parser')


def to_markdown(base_url: str, html: str) -> str:
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

    # Replace non-absolute URLs with absolute URLs
    markdown = string_utils.resolve_urls(base_url, markdown)
    return markdown.strip()
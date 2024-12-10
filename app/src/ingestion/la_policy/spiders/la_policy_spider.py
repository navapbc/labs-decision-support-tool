import pdb
import logging
import os
import re
import sys

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from pathlib import Path
from markdownify import markdownify

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag, PageElement

import scrapy
from scrapy.http import HtmlResponse
from scrapy.selector import Selector, SelectorList

app_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
print("Adding app folder to sys.path:", app_folder)
sys.path.append(app_folder)
from src.util import string_utils  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class ScrapingState:
    soup: BeautifulSoup
    current_list: Optional[Any] = None


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
        for li in lis[2:]:  # Start with "Programs" li. TODO: Remove slice
            href = li.css("a::attr(href)").get()
            if href != "#":
                page_url = f"{self.common_url_prefix}/{href}"
                logger.info("Found page URL %s", page_url)
                yield response.follow(page_url, callback=self.parse_page)
                # break

    def parse_page(self, response: HtmlResponse):
        logger.info("parse_page %s", response.url)

        # FIXME: Record critical sentences and ensure they exist in the output markdown
        Path(f"{response.url.split("/")[-1]}").write_bytes(response.body)
        Path(f"{response.url.split("/")[-1]}_0.md").write_text(
            to_markdown(self.common_url_prefix, response.text)
        )

        tables = response.xpath("body/table")
        assert len(tables) == 1, "Expected one top-level table"
        rows = response.xpath("body/table/tr")

        base_url = self.common_url_prefix
        header_md = to_markdown(rows[0].get(), base_url)
        assert (
            "Release Date" in header_md
        ), "Expected 'Release Date' in first row (which acts as page header)"

        markdown: list[str] = []
        # Convert table into headings and associated sections
        for row in rows[1:]:
            tds = row.xpath("./td")
            if len(tds) == 1:  # 1-column row
                p = tds[0].xpath("./p")
                p.get()
                p_class = p.attrib["class"]
                if p_class == "WD_ProgramName":
                    heading_md = "# " + to_markdown(self._parse_heading(p), base_url)
                elif p_class == "WD_SubjectLine":
                    heading_md = "## " + to_markdown(self._parse_heading(p), base_url)
                else:
                    # Some `p` tags do not have the `WD_SubjectLine` class
                    heading_md = "## " + to_markdown(self._parse_heading(p), base_url)
                    logger.warning("Assuming H2 heading: %r", heading_md)
                    # FIXME: https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-181_Processing_Redeterminations/40-181_Processing_Redeterminations.htm
                    # does not use the typical WD_ProgramName and WD_SubjectLine classes to identify H1 and H2 headings
                    # pdb.set_trace()
                markdown.append(heading_md)
            elif len(tds) == 2:  # 2-column row
                heading_md = "### " + to_markdown(self._parse_heading(tds[0]), base_url)
                section_md = self._parse_section(base_url, tds[1].get(), heading_level=3)
                markdown.append("\n\n".join([heading_md, section_md]))
            else:
                raise NotImplementedError(
                    f"Unexpected number of columns in row: {len(tds)}: {row.get()}"
                )
                pdb.set_trace()
        Path(f"{response.url.split("/")[-1]}.md").write_text("\n\n".join(markdown))

    def _parse_heading(self, cell: Selector) -> str:
        raw_texts = cell.xpath(".//text()").getall()
        return "".join(raw_texts)

    def _parse_section(self, base_url, html: str, heading_level: int) -> str:
        # Remove extraneous whitespace to simplify parsing
        min_html = "".join(line.strip() for line in html.split("\n"))
        soup = BeautifulSoup(min_html, "html.parser")

        body = soup.find("td")
        body.name = "div"
        self.__fix_body(heading_level, soup, body)

        # Replace underlined text with italicized text because markdown doesn't support underlining
        for tag in soup.find_all("u"):
            tag.name = "i"

        new_html = str(soup)
        section_md = to_markdown(new_html, base_url)
        section_md = re.sub(r"\n\n \n\n", "\n\n", section_md)
        return section_md

    def __fix_body(self, heading_level, soup, body):
        "Convert any tags so they can be appropriately converted to markdown"
        state = ScrapingState(soup)
        # Iterate over a copy of the contents since we may modify the contents
        for child in list(body.contents):
            if (child.name == "div" and len(child.contents) == 1):
                # For divs with only one child, ignore the div and process the child
                # Occurs for a table that is wrapped in a div for centering
                child = child.contents[0]

            if child.name == "p":
                # Handle lists presented as paragraphs
                self.__convert_any_paragraph_lists(state, child)
            elif child.name == "div":
                logger.warning("Unexpected div in body: %s", child)
                state2 = ScrapingState(soup)
                for c in list(child.contents):
                    if c.name == "p":
                        self.__convert_any_paragraph_lists(state2, c)
            elif child.name == "table":
                # If any table cell is large, then convert into a list
                if self._should_convert_table(child):
                    # TODO: Add _convert_table_to_list for columns > 2
                    self._convert_table_to_section(state, child, heading_level)
            elif isinstance(child, NavigableString):
                pass
            elif child.name in ["ul", "ol"]:
                pass
            else:
                print(child.name, child)
                pdb.set_trace()

    # FIXME: replace state with container for current_list
    def __convert_any_paragraph_lists(self, state: ScrapingState, para: Tag):
        if "WD_ListParagraphCxSpFirst" in para["class"]:
            if para.contents[0].get_text().strip() in "·":
                tag = "ul"
            else:
                tag = "ol"
            state.current_list = state.soup.new_tag(tag)
        if any(
            c
            in [
                "WD_ListParagraphCxSpFirst",
                "WD_ListParagraphCxSpMiddle",
                "WD_ListParagraphCxSpLast",
            ]
            for c in para["class"]
        ):
            if para.get_text().strip() == "":
                # Remove blank list items
                para.decompose()
                return

            para.name = "li"
            assert state.current_list is not None, "Expected current_list to be set"
            para.wrap(state.current_list)

            logger.debug("paragraph/list contents: %s", para.contents)
            # Remove extraneous space and bullet character at the beginning of para.contents
            for c in para.contents[:4]:
                stripped_text = c.get_text().strip()
                if c.name == "span":
                    if stripped_text in ["", "·"]:
                        # Removes `ltr` (left-to-right?) span -- not sure what this is for
                        # Removes the explicit bullet character and extra spaces
                        c.decompose()
                elif stripped_text == "" or re.match(r"^\d+\.", stripped_text):
                    # for NavigableString (raw text) which doesn't have decompose()
                    # Removes extraneous space (after bullet character)
                    # Removes number and period (e.g., "1.") that prefix ordered list items
                    c.extract()

            # Iterate over a copy of the contents since we may modify the contents
            # for c in list(para.contents):
            #     if c.name in [None, "br", "b", "u", "i", "sup", "span", "a", "strong", "em", "s"]:
            #         # "b" occurs for `<b><u>Note</u></b>`
            #         # "s" occurs for strike-through text but is blank
            #         pass
            #     else:
            #         logger.error("Unexpected in list item: %s", c.name, extra={"contents": para.contents})
            #         pdb.set_trace()

        if "WD_ListParagraphCxSpLast" in para["class"]:
            state.current_list = None

    def _should_convert_table(self, table: Tag) -> bool:
        # TODO: also check for nested tables or lists
        col_sizes = self._size_of_columns(table)
        if len(col_sizes) == 2:
            if col_sizes[1] > 2:
                return True
        return False

    def _size_of_columns(self, table: Tag) -> Sequence[int]:
        col_lengths: defaultdict[int, int] = defaultdict(int)
        for row in table.find_all("tr", recursive=False):
            for i, cell in enumerate(row.find_all(["td", "th"], recursive=False)):
                # TODO: Instead of text length, consider the number of tags
                # size = len(cell.get_text().strip())
                size = len([c for c in cell.contents if str(c).strip()])
                col_lengths[i] = max(col_lengths[i], size)
        return tuple(col_lengths.values())

    # FIXME: replace state arg with new_tag Callable
    def _convert_table_to_section(self, state: ScrapingState, table: Tag, heading_level: int):
        table_headings = []
        rows = table.find_all("tr", recursive=False)

        # Use first row as table headings if all cells are bold
        cols = rows[0].find_all(["td", "th"], recursive=False)
        assert len(cols) == 2, f"Expected 2 columns, got {len(cols)}: {cols}"
        if all(cell.find_all("b") for cell in cols):
            table_headings = [cell.get_text().strip() for cell in cols]
            rows[0].decompose()
            rows = rows[1:]
        else:
            # Since all cells are not bold, assume there are not table headings
            table_headings = ["" for _ in range(2)]

        for row in rows:
            row.name = "div"
            cols = row.find_all(["td", "th"], recursive=False)
            if len(cols) == 1:
                cols[0].name = f"h{heading_level + 1}"
            elif len(cols) == 2:
                cols[0].name = f"h{heading_level + 2}"
                if table_headings[0]:
                    heading_span = state.soup.new_tag("span")
                    heading_span.string = f"{table_headings[0]}: "
                    cols[0].contents[0].insert_before(heading_span)
                # pdb.set_trace()
                # replace_with(state.soup.new_tag(f"h{heading_level + 2}", f"{table_headings[0]}: {cols[0].get_text()}"))
                cols[1].name = "div"
                self.__fix_body(heading_level, state.soup, cols[1])
                if table_headings[1]:
                    heading_span = state.soup.new_tag("span")
                    heading_span.string = f"{table_headings[1]}: "
                    cols[1].contents[0].insert_before(heading_span)

        table.name = "div"
        # pdb.set_trace()


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
    return BeautifulSoup(test_html, "html.parser")


def to_markdown(html: str, base_url: Optional[str] = None) -> str:
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

    if base_url:
        # Replace non-absolute URLs with absolute URLs
        markdown = string_utils.resolve_urls(base_url, markdown)
    return markdown.strip()

import os
import pdb
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import scrapy
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.selector import Selector

app_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
print("Adding app folder to sys.path:", app_folder)
sys.path.append(app_folder)
from src.util import string_utils  # noqa: E402


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
        if False:
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-407_Work_Registration/63-407_Work_Registration.htm"
            page_url = "/Users/yoom/dev/labs-decision-support-tool/app/src/ingestion/44-350_Overpayments.htm"
            # page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-504_ESAP_Waiver_for_Elderly_and_Disabled_Households/63-504_ESAP_Waiver_for_Elderly_and_Disabled_Households.htm"

            # "Cannot insert None into a tag."
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm"
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CAPI/CAPI/49-015_CAPI_Application_Process/49-015_CAPI_Application_Process.htm"
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-211_552_Moving_Assistance_Program/44-211_552_Moving_Assistance_Program.htm"
            # NotImplementedError: Unexpected number of columns in row: 3
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members/40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm"

            # Expected one paragraph in heading row: <tr>
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/SSI_SSP_COLA/SSI_SSP_COLA.htm"

            yield response.follow(page_url, callback=self.parse_page)
        else:
            lis = response.css("li.book")
            for li in lis[2:]:  # Start with "Programs"-related pages. TODO: Remove slice
                href = li.css("a::attr(href)").get()
                if href != "#":
                    page_url = f"{self.common_url_prefix}/{href}"
                    # self.logger.info("Found page URL %s", page_url)
                    yield response.follow(page_url, callback=self.parse_page)

    def parse_page(self, response: HtmlResponse):
        self.logger.info("parse_page %s", response.url)
        # Save html file for debugging
        filepath = "./scraped/" + response.url.removeprefix(self.common_url_prefix + "/mergedProjects/")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        Path(filepath).write_bytes(response.body)

        tables = response.xpath("body/table")
        rows = tables[0].xpath("./tr")

        # assert len(tables) == 1, "Expected one top-level table"
        # FIXME: https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-407_Work_Registration/63-407_Work_Registration.htm
        # has a table that is outside the top-level table
        # pdb.set_trace()

        header_md = to_markdown(rows[0].get())
        assert (
            "Purpose" in header_md and "Policy" in header_md
        ), "Expected 'Purpose' and 'Policy' in first row (which acts as page header)"
        # Ignore the first row, which is the page header boilerplate
        rows = rows[1:]

        # Convert table rows into headings and associated sections
        markdown: list[str] = [
            self._convert_to_headings_and_sections(row, self.common_url_prefix) for row in rows
        ]

        Path(f"{filepath}.md").write_text(
            f"[Source page]({response.url})\n\n" + "\n\n".join(markdown), encoding="utf-8"
        )

    def _convert_to_headings_and_sections(self, row: Selector, base_url: str) -> str:
        # FIXME: Record critical sentences and ensure they exist in the output markdown
        tds = row.xpath("./td")
        # A 1-column row represents top-level headings
        if len(tds) == 1:
            paras = tds[0].xpath("./p")
            if len(paras) > 1:
                self.logger.warning("Expected only one <p> in 1-col heading rows: %s", row.get())
            heading_md = []
            for para in paras:
                p_class = para.attrib["class"]
                if p_class == "WD_ProgramName":
                    heading_md.append("# " + to_markdown(self._parse_heading(para), base_url))
                elif p_class == "WD_SubjectLine":
                    heading_md.append("## " + to_markdown(self._parse_heading(para), base_url))
                elif (text := para.xpath(".//text()").get()) and text.strip():
                    # Some `p` tags don't have the `WD_SubjectLine` class when it should
                    assumed_heading = "## " + to_markdown(self._parse_heading(para), base_url)
                    self.logger.warning("Assuming H2 heading: %r", assumed_heading)
                    heading_md.append(assumed_heading)
                    # FIXME: https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-181_Processing_Redeterminations/40-181_Processing_Redeterminations.htm
                    # does not use the typical WD_ProgramName and WD_SubjectLine classes to identify H1 and H2 headings
                    # pdb.set_trace()
            return "\n".join(heading_md)

        if len(tds) == 3:
            # In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm, there's an erroneous empty 3rd column
            # Remove the empty 3rd column and let the next block handle the 2-column rows
            if not tds[2].xpath(".//text()").get().strip():
                tds[2].remove()
                tds = row.xpath("./td")
            else:
                raise AssertionError(f"Unexpected 3-column row has text: {tds[2].get()}")

        if len(tds) == 2:  # 2-column row
            # FIXME: look for "WD_SectionHeading" class in the first column
            subheading_md = "### " + to_markdown(self._parse_heading(tds[0]), base_url)
            section_md = self._parse_section(base_url, tds[1].get(), heading_level=3)
            return "\n\n".join([subheading_md, section_md])

        raise NotImplementedError(f"Unexpected number of columns in row: {len(tds)}: {row.get()}")

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
            if (
                child.name == "div"
                and len(child.contents) == 1
                and child.contents[0].name == "table"
            ):
                # For divs with only one child, ignore the div and process the child
                # Occurs for a table that is wrapped in a div for centering
                child = child.contents[0]

            if child.name == "p":
                # Handle lists presented as paragraphs
                self.__convert_any_paragraph_lists(state, child)
            elif child.name == "div":
                self.logger.warning("Unexpected div in body: %s", child)
                state2 = ScrapingState(soup)
                for c in list(child.contents):
                    if c.name == "p":
                        self.__convert_any_paragraph_lists(state2, c)
            elif child.name == "table":
                # If any table cell is large, then convert table to heading sections
                if self._should_convert_table(child):
                    self._convert_table_to_sections(state, child, heading_level)
            elif isinstance(child, NavigableString) or child.name in ["ul", "ol"]:
                pass
            else:
                print(child.name, child)
                pdb.set_trace()

    # FIXME: replace state with container for current_list
    def __convert_any_paragraph_lists(self, state: ScrapingState, para: Tag):
        if "class" not in para.attrs:
            return

        if "WD_ListParagraph" in para["class"]:  # Often used for ordered lists
            if state.current_list is None:
                # Use `ul` tag rather than `ol` since we're going to leave the explicit numbering alone
                state.current_list = state.soup.new_tag("ul")
            # CalFresh/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm
            # incorrectly uses a mix of both in the same list

        if "WD_ListParagraphCxSpFirst" in para["class"]:
            # Use `ul` tag even if it's an ordered list since we're going to leave the explicit numbering alone
            state.current_list = state.soup.new_tag("ul")
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
            # In 44-350_Overpayments, a table is erroneously interleaved with the list;
            # the table start with a WD_ListParagraphCxSpMiddle and ends with WD_ListParagraphCxSpLast
            if state.current_list is None:
                # In CalFresh/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm
                # incorrectly uses a mix of both in the same list
                self.logger.warning("Improperly annotated list item! Creating a new list.")
                state.current_list = state.soup.new_tag("ul")

            self.logger.debug("paragraph/list contents: %s", para.contents)
            para.wrap(state.current_list)
            # Remove extraneous space and bullet character at the beginning of para.contents
            for c in para.contents[:4]:
                stripped_text = c.get_text().strip()
                if c.name == "span":
                    if stripped_text in ["", "·"]:
                        # Removes `ltr` (left-to-right?) span -- not sure what this is for
                        # Removes the explicit bullet character and extra spaces
                        c.decompose()
                elif stripped_text == "":
                    # for NavigableString (raw text) which doesn't have decompose()
                    # Removes extraneous space (after bullet character)
                    # Removes number and period (e.g., "1.") that prefix ordered list items
                    c.extract()

        if "WD_ListParagraphCxSpLast" in para["class"]:
            state.current_list = None

    def _should_convert_table(self, table: Tag) -> bool:
        # FIXME: In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members/40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm
        # many occurrences of a list inappropriately wrapped in a table and is rendered as a curious table in markdown
        col_sizes = self._size_of_columns(table)
        if len(col_sizes) == 2:
            # First column is usually short
            # If the second column is long, then convert the table
            # TODO: Check for nested tables or lists in the second column
            if col_sizes[1] > 2:
                return True
        if len(col_sizes) > 2:
            self.logger.warning("Leaving %s-column tables alone: %s", len(col_sizes), col_sizes)
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
    def _convert_table_to_sections(self, state: ScrapingState, table: Tag, heading_level: int):
        table_headings = []
        rows = table.find_all("tr", recursive=False)

        # Use first row as table headings if all cells are bold
        cols = rows[0].find_all(["td", "th"], recursive=False)
        if len(cols) == 2 and all(cell.find_all("b") for cell in cols):
            # Since all cells are bold, treat them as table headings
            table_headings = [cell.get_text().strip() for cell in cols]
            rows[0].decompose()
            rows = rows[1:]
        else:
            # Since all cells are not bold, assume they are not table headings
            table_headings = ["" for _ in range(2)]

        for row in rows:
            cols = row.find_all(["td", "th"], recursive=False)
            if len(cols) == 1:
                # Treat single column rows as a heading
                row.name = "div"
                cols[0].name = f"h{heading_level + 1}"
            elif len(cols) == 2:
                # Treat 2-column rows as a subheading and its associated body
                row.name = "div"
                cols[0].name = f"h{heading_level + 2}"
                if table_headings[0]:
                    heading_span = state.soup.new_tag("span")
                    heading_span.string = f"{table_headings[0]}: "
                    cols[0].contents[0].insert_before(heading_span)
                cols[1].name = "div"
                self.__fix_body(heading_level, state.soup, cols[1])
                if table_headings[1]:
                    heading_span = state.soup.new_tag("span")
                    heading_span.string = f"{table_headings[1]}: "
                    cols[1].contents[0].insert_before(heading_span)
            else:
                self.logger.warning(
                    "Unexpected number of columns in table row: %s: %r", len(cols), cols.strings
                )

        table.name = "div"


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

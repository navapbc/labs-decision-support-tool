import os
import pdb
import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import scrapy
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.selector import Selector

from src.util import string_utils
from src.util.string_utils import count_diffs


@dataclass
class ScrapingState:
    soup: BeautifulSoup = field(repr=False)
    current_list: Optional[Any] = None


@dataclass
class PageState:
    filename: str
    title: str
    soup: BeautifulSoup = field(repr=False)

    h1: Optional[str] = None
    h2: Optional[str] = None


class LA_PolicyManualSpider(scrapy.Spider):
    name = "la_policy_spider"

    # TODO: Port playwrite code to scrapy via https://github.com/scrapy-plugins/scrapy-playwright?tab=readme-ov-file#executing-actions-on-pages
    start_urls = [
        # To create this html file:
        #   cd app/src/ingestion/la_policy/scrape
        #   pip install -r requirements.txt
        #   python scrape_la_policy_nav_bar.py
        Path(os.path.abspath("./la_policy/scrape/la_policy_nav_bar.html")).as_uri(),
    ]

    common_url_prefix = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster"

    DEBUGGING = False

    def start_requests(self) -> Iterable[scrapy.Request]:
        if self.DEBUGGING:
            urls = [
                "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Organ_Transplant_AntiRejection_Medications/Organ_Transplant_AntiRejection_Medications.htm",
            ]
            for url in urls:
                yield scrapy.Request(url=url, callback=self.parse_page)
        else:
            for url in self.start_urls:
                yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response: HtmlResponse) -> Iterable[scrapy.Request]:
        lis = response.css("li.book")
        for li in lis:
            href = li.css("a::attr(href)").get()
            if href == "#":
                continue

            name = "".join([t for t in li.xpath(".//text()").getall() if t.strip()])
            page_url = f"{self.common_url_prefix}/{href}"
            self.logger.debug("URL for %r => %s", name, page_url)
            yield response.follow(page_url, callback=self.parse_page)

    # Return value is saved to filename set by scrape_la_policy.OUTPUT_JSON
    def parse_page(self, response: HtmlResponse) -> dict[str, str]:
        url = response.url
        title = response.xpath("head/title/text()").get().strip()
        self.logger.info("parse_page %s", url)
        extractions = {"url": url}

        # 40-101_19_Extended_Foster_Care_Benefits.htm and 1210_Overview.htm have extra '\r\n' and
        # results in missing spaces in markdown text -- `replace("\r\n", "")` fixes this :shrug:
        soup = BeautifulSoup(response.body.decode("utf-8").replace("\r\n", ""), "html.parser")
        response = None  # Don't use old response
        smoothed_html = soup.prettify()

        filepath = "./scraped/" + url.removeprefix(self.common_url_prefix + "/mergedProjects/")
        debug_scrapings = bool(os.environ.get("DEBUG_SCRAPINGS", False))
        if debug_scrapings:
            # Save html file for debugging
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            Path(filepath).write_text(smoothed_html, encoding="utf-8")

        page_state = PageState(filename=url.split("/")[-1], title=title, soup=soup)
        self._extract_and_remove_top_headings(self.common_url_prefix, page_state)
        assert page_state.h1 and page_state.h2, f"Expecting H1 and H2 to be set: {page_state}"
        self.__check_h2(page_state)

        smoothed_response = Selector(text=soup.prettify())
        tables = smoothed_response.xpath("body/table")
        rows = tables[0].xpath("./tr")
        header_md = to_markdown(rows[0].get())
        assert (
            "Purpose" in header_md and "Policy" in header_md
        ), "Expected 'Purpose' and 'Policy' in first row (which acts as page header)"
        # Ignore the first row, which is the page header boilerplate
        # TODO: Extract "Release Date" value
        rows = rows[1:]

        # Convert table rows into headings and associated sections
        md_list: list[str] = [
            self._convert_to_headings_and_sections(row, self.common_url_prefix) for row in rows
        ]

        # 63-407_Work_Registration.htm has a table that is outside the main top-level table
        for table in tables[1:]:
            self.logger.info("Scraping extra table after main table: %s")
            rows = table.xpath("./tr")
            for row in rows:
                md_list.append(self._convert_to_headings_and_sections(row, self.common_url_prefix))

        markdown = "\n\n".join(md_list)
        if debug_scrapings:
            Path(f"{filepath}.md").write_text(
                f"[Source page]({url})\n\n" + markdown, encoding="utf-8"
            )

        # check that h1 is one of the 10 programs
        if page_state.h1.casefold() not in self.KNOWN_PROGRAMS:
            self.logger.error("Unknown program: %s", page_state.h1)

        # More often than not, the h2 is better suited as the title
        # Also 44-211_2_Recurring_Special_Needs.htm has the wrong title
        extractions["h2"] = page_state.h2
        extractions["title"] = page_state.title
        extractions["markdown"] = markdown
        return extractions

    KNOWN_PROGRAMS = {
        program.casefold()
        for program in [
            "CAPI",
            "CalFresh",
            "CalWORKs",
            "Child Care",
            "GAIN",
            "GAIN/GROW",
            "GR",
            "GENERAL RELIEF",
            "GROW",
            "IHSS",
            "IN-HOME SUPPORTIVE SERVICES",
            "IN-HOME SUPPORTIVE SERVICES PROGRAM",
            "Medi-Cal",
            "MEDI-CAL PROGRAM",
            "REP",
            "REFUGEE EMPLOYMENT PROGRAM",
        ]
    }

    def _h1_paragraphs(self, rows: list[Tag]) -> Sequence[Tag]:
        return self.__flatten_and_filter_out_blank(
            rows, lambda row: row.find_all("p", class_="WD_ProgramName")
        )

    def _h2_paragraphs(self, rows: list[Tag]) -> Sequence[Tag]:
        return self.__flatten_and_filter_out_blank(
            rows, lambda row: row.find_all("p", class_="WD_SubjectLine")
        )

    def _nonempty_paragraphs(self, rows: list[Tag]) -> Sequence[Tag]:
        return self.__flatten_and_filter_out_blank(rows, lambda row: row.find_all("p"))

    def __flatten_and_filter_out_blank(
        self, rows: list[Tag], resultset_generator: Callable
    ) -> Sequence[Tag]:
        return [
            para
            for para in chain(*[resultset_generator(row) for row in rows])
            if para.get_text().strip()
        ]

    def _linked_nonempty_paragraphs(self, tag: Tag) -> Sequence[Tag]:
        return [
            span.parent
            for span in tag.find_all("span", class_="WD_Hyperlink")
            if span.parent.get_text().strip()
        ]

    def _extract_and_remove_top_headings(self, base_url: str, pstate: PageState) -> None:
        "Extract the H1 and H2 headings from the top of the page and remove them so they don't get processed"
        soup = pstate.soup
        table = soup.find("table")
        # 69-202_1_Identification_of_Refugees incorrectly uses WD_SubjectLine for non-heading text "Amerasian" in the body
        # so only look at the first few rows
        # In Pickle_Program.htm, the H1 and H2 are in the first row (they're typically in the second row)
        top_rows = table.find_all("tr", recursive=False, limit=3)

        self.__handle_priority_special_cases(base_url, pstate, table)
        # self.logger.info("post-priority: %s:", pstate)
        if pstate.h1 and pstate.h2:
            return

        for para in self._h1_paragraphs(top_rows):
            h1 = to_markdown(para.get_text(), base_url)
            if not pstate.h1:
                pstate.h1 = h1
                para.decompose()
            elif self._handle_extra_h1(pstate, h1):
                para.decompose()
            else:
                self.logger.error("Extra H1 (WD_ProgramName) heading: %r %s", h1, pstate)

        for para in self._h2_paragraphs(top_rows):
            h2 = to_markdown(para.get_text(), base_url)
            if not pstate.h2:
                pstate.h2 = h2
                para.decompose()
            elif self._handle_extra_h2(pstate, h2):
                para.decompose()
            else:
                self.logger.error("Extra H2 (WD_SubjectLine) heading: %r %s", h2, pstate)

        self.logger.info("post-typical: %s", pstate)
        if pstate.h1 and pstate.h2:
            return

        self.__handle_special_cases(base_url, pstate, table)
        self.logger.info("post-special: %s", pstate)

        if self.DEBUGGING and (not pstate.h1 or not pstate.h2):
            pdb.set_trace()

    def __handle_priority_special_cases(self, base_url: str, pstate: PageState, table: Tag) -> None:
        "Needs to be handled before parsing the typical headings"
        top_rows = table.find_all("tr", recursive=False, limit=3)

        if len(self._h1_paragraphs(top_rows)) == 0 and (h2s := self._h2_paragraphs(top_rows)):
            # e.g., 44-211_552_Moving_Assistance_Program, 40-100_National_Voter_Registration_Act_-_Kick-Off
            # These misclassifies H1 heading as a WD_SubjectLine,
            # so there are multiple WD_SubjectLine and no WD_ProgramName
            assert not pstate.h1, f"Unexpected missing H1: {pstate}"
            first_para = h2s[0]
            pstate.h1 = to_markdown(first_para.get_text(), base_url)
            first_para.decompose()
            self.logger.info("Using first H2 for missing H1: %s", pstate.h1)

    def _handle_extra_h1(self, pstate: PageState, h2: str) -> bool:
        if pstate.filename in [
            "4_1_1__GROW_Transition_Age_Youth_Employment_Program.htm",
            "4_1_2_GROW_Youth_Employment_Program.htm",
            "63-407_Work_Registration.htm",
            "63-802_Restoration_of_Lost_Benefits.htm",
        ]:
            # These incorrectly have multiple WD_ProgramName and no WD_SubjectLine
            # so use WD_ProgramName in subsequent rows as H2.
            if not pstate.h2:
                pstate.h2 = h2
                self.logger.info("Using WD_ProgramName as H2: %s", pstate.h2)
                return True
        return False

    def _handle_extra_h2(self, pstate: PageState, h2: str) -> bool:
        # SSI_SSP_COLA/SSI_SSP_COLA.htm has multiple WD_SubjectLine in the same td
        # so merge them into a single H2
        if pstate.filename == "SSI_SSP_COLA.htm":
            assert pstate.h2, "Expected H2 to be set"
            pstate.h2 += " " + h2
            return True
        return False

    def __handle_special_cases(self, base_url: str, pstate: PageState, table: Tag) -> None:
        # The following handles atypical pages

        if pstate.filename == "2_3_Comprehensive_Intake_and_Employability_Assessment.htm":
            pstate.h2 = pstate.title
            self.logger.info("Missing H2; using title as H2: %s", pstate)
            return

        top_rows = table.find_all("tr", recursive=False, limit=3)

        def set_headings_by_order(paras: Sequence[Tag]) -> None:
            for para in paras:
                md_text = to_markdown(para.get_text(), base_url)
                if not md_text.strip():
                    continue
                if not pstate.h1:
                    pstate.h1 = md_text
                    para.decompose()
                elif not pstate.h2:
                    pstate.h2 = md_text
                    para.decompose()
            self.logger.warning("Missing H1,H2 headings; used first likely paragraphs: %s", pstate)

        # In Organ_Transplant_AntiRejection_Medications.htm the H1 and H2 are in the ignored first row
        # Plus Organ_Transplant_AntiRejection_Medications doesn't use WD_ProgramName and WD_SubjectLine
        if pstate.filename == "Organ_Transplant_AntiRejection_Medications.htm":
            paras = top_rows[0].find("td").find_all("p", recursive=False)
            set_headings_by_order(paras)
            return

        # 40-181_Processing_Redeterminations doesn't use WD_ProgramName or WD_SubjectLine
        # Residency_for_Out-of-State_Students doesn't use WD_SubjectLine
        # At this point, we can't rely on class annotations, just parse based on order of paragraphs
        # H1 and H2 headings are typically in the second row, so exclude the first row to avoid parsing the page header
        set_headings_by_order(self._nonempty_paragraphs(top_rows[1:]))

        for para in self._nonempty_paragraphs(top_rows[1:]):
            self.logger.error("Extra heading: %r", para.get_text())

    def __check_h2(self, page_state: PageState) -> None:
        assert page_state.h2
        if (
            (page_state.h2.casefold() not in page_state.title.casefold())
            and (page_state.title.casefold() not in page_state.h2.casefold())
            and (
                count_diffs(page_state.h2.casefold(), page_state.title.casefold())
                / len(page_state.title)
                > 0.7
            )
        ):
            if page_state.filename in [
                "SSI_SSP_COLA.htm",
                "ABLE_and_CalABLE_Accounts_in_the_CalFresh_Program.htm",
            ]:
                # These have been manually reviewed and are expected to have a different H2
                return

            self.logger.info("H2 is significantly different from the page title: %s", page_state)
            if not page_state.h2[0].isdigit() and len(page_state.h2) > 100:
                self.logger.warning("H2 heading may not be a heading: %s", page_state.h2)

    def _convert_to_headings_and_sections(self, row: Selector, base_url: str) -> str:
        # TODO: Record sentences and ensure they exist in the output markdown
        tds = row.xpath("./td")

        if len(tds) == 1:
            # Near the bottom of 69-202_1_Identification_of_Refugees.htm, the row becomes 1-column
            # because there's a div-wrapped table. The row should have been part of the previous row.
            # Treat the single-column row as if it was the second column of a 2-column row
            return self._parse_section(base_url, tds[0].get(), heading_level=3)

        if len(tds) == 8:
            # At the bottom of 63-900_Emergency_CalFresh_Assistance.htm is an extra table with 8 columns;
            # just render it as a table
            return to_markdown(row.get(), base_url)

        if len(tds) == 3:
            # In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm, there's an erroneous empty 3rd column
            # Remove the empty 3rd column and let the next block handle the 2-column rows
            if not tds[2].xpath(".//text()").get().strip():
                tds[2].remove()
                tds = row.xpath("./td")
            else:
                raise AssertionError(f"Unexpected 3-column row has text: {tds[2].get()}")

        if len(tds) == 2:  # 2-column row
            subheading_md = "### " + to_markdown(self._parse_heading(tds[0]), base_url)
            paras = tds[0].xpath("./p")
            if not [para.attrib["class"] == "WD_SectionHeading" for para in paras]:
                # minor inconsistency; mitigation: assume first column is a subheading
                self.logger.info(
                    "Assuming subheading (despite lack of WD_SectionHeading): %s", subheading_md
                )

            section_md = self._parse_section(base_url, tds[1].get(), heading_level=3)
            return "\n\n".join([subheading_md, section_md])

        raise NotImplementedError(f"Unexpected number of columns in row: {len(tds)}: {row.get()}")

    TYPICAL_SUBHEADINGS = {
        "Purpose",
        "Policy",
        "Background",
        "Definition",
        "Requirements",
        "Verification Docs",
    }

    def _parse_heading(self, cells: Selector) -> str:
        raw_texts = cells.xpath(".//text()").getall()
        return " ".join(raw_texts)
        # return " ".join([text.strip() for text in raw_texts if text.strip()])

    def _parse_section(self, base_url: str, html: str, heading_level: int) -> str:
        # Remove extraneous whitespace to simplify parsing
        min_html = "".join(line.strip() for line in html.split("\n"))  # .replace("\r\n", "\n")
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

    def __fix_body(
        self, heading_level: int, soup: BeautifulSoup, body: Tag | NavigableString
    ) -> None:
        "Convert any tags so they can be appropriately converted to markdown"
        state = ScrapingState(soup)
        # Iterate over a copy of body.contents since we may modify the contents
        for child in list(body.contents):
            if (
                child.name == "div"
                and len(child.contents) == 1
                and child.contents[0].name in ["table", "p"]
            ):
                # For divs with only one child, ignore the div and process the child
                # Occurs for a table that is wrapped in a div for centering
                child = child.contents[0]

            if child.name == "p":
                # Handle lists presented as paragraphs
                self.__convert_any_paragraph_lists(state, child)
            elif child.name == "div":
                # 63-405_Citizenship_or_Eligible_Non-Citizen_Status.htm has a div wrapping several <p> tags
                self.logger.info("Atypical div wrapping several tags: %s", child)
                self.__fix_body(heading_level, soup, child)
            elif child.name == "table":
                # TODO: Check table for 1-col rows and convert them to headings -- see _convert_table_to_sections
                if self._should_convert_table(child):
                    self._convert_table_to_sections(state, child, heading_level)
            elif isinstance(child, NavigableString) or child.name in ["ul", "ol"]:
                pass
            elif child.get_text().strip() == "":
                pass
            else:
                raise NotImplementedError(f"Unexpected {child.name}: {child}")

    # FIXME: replace state with container for current_list and new_tag Callable
    def __convert_any_paragraph_lists(self, state: ScrapingState, para: Tag) -> None:
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
        # row_text = [td.text for td in table.find("tr").find_all(["td", "th"], recursive=False)]
        # self.logger.debug("_should_convert_table: %r", row_text)

        if self._table_uses_rowspan(table):
            row_text = [td.text for td in table.find("tr").find_all(["td", "th"], recursive=False)]
            # 69-202_1_Identification_of_Refugees.htm
            self.logger.info("Leaving table using rowspan as is: %s", row_text)
            return False

        # TODO: In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm
        # many occurrences of a list inappropriately wrapped in a table and is rendered as a curious table in markdown
        col_sizes = self._size_of_columns(table)
        if len(col_sizes) == 2:
            # First column is usually short and often acts as a heading
            # If the second column is long, then convert the table
            # TODO: Check for nested tables or lists in the second column
            if col_sizes[1] > 2:
                return True

        if len(col_sizes) > 2:
            row_text = [td.text for td in table.find("tr").find_all(["td", "th"], recursive=False)]
            self.logger.info(
                "Leaving %s-column table as is: %s: %r", len(col_sizes), col_sizes, row_text
            )
            return False

        return False

    def _table_uses_rowspan(self, table: Tag) -> bool:
        for row in table.find_all("tr", recursive=False):
            for cell in row.find_all(["td", "th"], recursive=False):
                if "rowspan" in cell.attrs and int(cell.attrs["rowspan"]) > 1:
                    # TODO: handle non-default rowspans in 69-202_1_Identification_of_Refugees.htm
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

    def __table_row_is_heading(self, first_row_cols: Sequence[Tag]) -> bool:
        # If all columns are bold, then treat the row as a heading
        if all(cell.find_all("b") for cell in first_row_cols):
            return True

        # If all columns have a p tag using WD_TableHeading class, then treat the row as a heading
        if [
            cell
            for cell in first_row_cols
            if cell.find_all("p", attrs={"class": "WD_TableHeading"})
        ] == first_row_cols:
            return True
        return False

    # FIXME: replace state arg with new_tag Callable
    def _convert_table_to_sections(
        self, state: ScrapingState, table: Tag, heading_level: int
    ) -> None:
        rows = table.find_all("tr", recursive=False)

        # Use first row as table headings if all cells are bold
        cols = rows[0].find_all(["td", "th"], recursive=False)
        if len(cols) == 2 and self.__table_row_is_heading(cols):
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


# TODO: if possible, consolidate with edd_spider.to_markdown()
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

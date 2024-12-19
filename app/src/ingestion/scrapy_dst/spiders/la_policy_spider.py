import os
import pdb
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import chain
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import html2text
import scrapy
from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag
from scrapy.http import HtmlResponse
from scrapy.selector import Selector

from src.ingestion.markdown_tree import normalize_markdown
from src.util.string_utils import count_diffs


@dataclass
class HtmlListState:
    soup: BeautifulSoup = field(repr=False)
    current_list: Optional[Any] = None


@dataclass
class PageState:
    filename: str
    title: str
    soup: BeautifulSoup = field(repr=False)

    h1: Optional[str] = None
    h2: Optional[str] = None


class TargetElementType(Enum):
    NONE = auto()
    LIST = auto()
    SECTIONS = auto()  # headings with associated sections
    RAW_TEXT = auto()  # extract raw text
    BODY = auto()  # body without heading


# 42-431_2_Noncitizen_Status.htm, 42-200_Property.htm use all these as bullets
BULLETS = ["·", "•", "Ø", "o", "§"]


class LA_PolicyManualSpider(scrapy.Spider):
    name = "la_policy_spider"

    # TODO: Port playwrite code to scrapy via https://github.com/scrapy-plugins/scrapy-playwright?tab=readme-ov-file#executing-actions-on-pages
    start_urls = [
        # To create this la_policy_nav_bar.html file:
        #   cd app/src/ingestion/la_policy/scrape
        #   pip install -r requirements.txt
        #   python scrape_la_policy_nav_bar.py
        Path(os.path.abspath("./la_policy/scrape/la_policy_nav_bar.html")).as_uri(),
    ]

    common_url_prefix = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster"

    DEBUGGING = os.environ.get("DEBUGGING", False)

    def start_requests(self) -> Iterable[scrapy.Request]:
        if self.DEBUGGING:
            urls = [
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GR/GR/40-101_19_Extended_Foster_Care_Benefits/40-101_19_Extended_Foster_Care_Benefits.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Child%20Care/Child_Care/1210_Overview/1210_Overview.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/42-431_2_Noncitizen_Status/42-431_2_Noncitizen_Status.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-504_39_CalFresh_COLA/63-504_39_CalFresh_COLA.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/43-109_Unrelated_Adult_Male/43-109_Unrelated_Adult_Male.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/42-200_Property/42-200_Property.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/89-201_Minor_Parent/89-201_Minor_Parent.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/42-405_Absence_from_California/42-405_Absence_from_California.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-405_Citizenship_or_Eligible_Non-Citizen_Status/63-405_Citizenship_or_Eligible_Non-Citizen_Status.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-105_40_Immunizations/40-105_40_Immunizations.htm",
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GR/GR/46-102_Single_Adult_Model/46-102_Single_Adult_Model.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GAIN/GAIN/610_SIP_Approval/610_SIP_Approval.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-402_4_Residents_of_Institutions/63-402_4_Residents_of_Institutions.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-503_49_Sponsored_Noncitizen/63-503_49_Sponsored_Noncitizen.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/42-300_Time_Limit_Requirements/42-300_Time_Limit_Requirements.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-503_41_Self-Employment_Income/63-503_41_Self-Employment_Income.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GR/GR/44-220_Emergency_Aid/44-220_Emergency_Aid.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm"
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-211_561_Homeless_Case_Management_Program/44-211_561_Homeless_Case_Management_Program.htm"
                # FIXME: Why Term-Definition not supported?
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Social_Security_Requirement/Social_Security_Requirement.htm"
                # FIXME: Why Term-Description not supported? 'Leaving table as is: (1, 1): ['Term', 'Description']'
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Retroactive_Medi-Cal_for_Individuals_Transitioning_from_APTC/Retroactive_Medi-Cal_for_Individuals_Transitioning_from_APTC.htm"
                # FIXME: WARNING: Improperly annotated list item! Creating a new list for 'Definition'
                # "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Coverage_for_Immigrants/Coverage_for_Immigrants.htm"
            ]
            for url in urls:
                yield scrapy.Request(url=url, callback=self.parse_page)
        else:
            for url in self.start_urls:
                yield scrapy.Request(url=url, callback=self.parse)

    # region ============= Parsing entrypoints

    def parse(self, response: HtmlResponse) -> Iterable[scrapy.Request]:
        "Parses navigation menu to extract URLs for scraping content pages"
        lis = response.css("li.book")
        for li in lis:
            href = li.css("a::attr(href)").get()
            if href == "#":
                continue

            name = "".join([t for t in li.xpath(".//text()").getall() if t.strip()])
            page_url = f"{self.common_url_prefix}/{href}"
            self.logger.debug("URL for %r => %s", name, page_url)
            yield response.follow(page_url, callback=self.parse_page)

    def parse_page(self, response: HtmlResponse) -> dict[str, str]:
        "Parses content pages; return value is add to file set by scrape_la_policy.OUTPUT_JSON"
        url = response.url
        title = response.xpath("head/title/text()").get().strip()
        self.logger.info("parse_page %s", url)
        soup = BeautifulSoup(response.body, "html.parser")

        filepath = "./scraped/" + url.removeprefix(self.common_url_prefix + "/mergedProjects/")
        debug_scrapings = bool(os.environ.get("DEBUG_SCRAPINGS", False))
        if debug_scrapings:
            # Save html file for debugging
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            Path(filepath).write_bytes(response.body)

        page_state = PageState(filename=url.split("/")[-1], title=title, soup=soup)
        self._extract_and_remove_top_headings(self.common_url_prefix, page_state)
        assert page_state.h1 and page_state.h2, f"Expecting H1 and H2 to be set: {page_state}"
        self._check_h2_validity(page_state)

        modified_response = Selector(text=str(page_state.soup))
        tables = modified_response.xpath("body/table")
        rows = tables[0].xpath("./tr")
        header_md = to_markdown(rows[0].get())
        assert (
            "Purpose" in header_md and "Policy" in header_md
        ), "Expected 'Purpose' and 'Policy' in first row (which acts as page header)"
        # Ignore the first row, which is the page header boilerplate
        # TODO: Extract "Release Date" value
        rows = rows[1:]

        # Convert table rows into headings and associated sections
        md_list: list[str] = [f"# {page_state.h1}", f"## {page_state.h2}"]
        md_list += [
            self._headings_and_sections_to_markdown(row, self.common_url_prefix) for row in rows
        ]

        # 63-407_Work_Registration.htm has a table that is outside the main top-level table
        for table in tables[1:]:
            self.logger.info("Scraping extra table after main table: %s")
            rows = table.xpath("./tr")
            for row in rows:
                md_list.append(self._headings_and_sections_to_markdown(row, self.common_url_prefix))

        # Check that h1 is one of the 10 programs
        if page_state.h1.casefold() not in self.KNOWN_PROGRAMS:
            self.logger.error("Unknown program: %r", page_state.h1)

        # Fixes
        if page_state.filename == "44-211_2_Recurring_Special_Needs.htm":
            # has the wrong title "44-211.52 Temporary Homeless Assistance"
            page_state.title = page_state.h2

        # TODO: Add checks to ensure original sentences exist in the resulting markdown
        markdown = "\n\n".join([md for md in md_list if md.strip()])
        if debug_scrapings:
            # Use normalize_markdown() like it is used before chunking
            Path(f"{filepath}.md").write_text(
                f"[Source page]({url})\n\n" + normalize_markdown(markdown), encoding="utf-8"
            )

        # More often than not, the h2 heading is better suited as the title
        extractions = {
            "url": url,
            "title": page_state.title,
            "h1": page_state.h1,
            "h2": page_state.h2,
            "markdown": markdown,
        }
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

    # endregion
    # region ============= Heading H1 and H2 extraction functions

    def _extract_and_remove_top_headings(self, base_url: str, pstate: PageState) -> None:
        "Extract the H1 and H2 headings from the top of the page and remove them so they don't get processed"
        soup = pstate.soup
        table = soup.find("table")
        # 69-202_1_Identification_of_Refugees incorrectly uses WD_SubjectLine for non-heading text "Amerasian" in the body
        # so only look at the first few rows
        # In Pickle_Program.htm, the H1 and H2 are in the first row (they're typically in the second row)
        top_rows = table.find_all("tr", recursive=False, limit=3)

        self.__handle_h1_special_cases(base_url, pstate, table)

        for para in _h1_paragraphs(top_rows):
            h1 = to_markdown(para.get_text(), base_url)
            if not pstate.h1:
                pstate.h1 = h1
                para.decompose()
            elif self.__handle_extra_h1(pstate, h1):
                para.decompose()
            else:
                self.logger.error("Extra H1 (WD_ProgramName) heading: %r %s", h1, pstate)

        for para in _h2_paragraphs(top_rows):
            h2 = to_markdown(para.get_text(), base_url)
            if not pstate.h2:
                pstate.h2 = h2
                para.decompose()
            elif self.__handle_extra_h2(pstate, h2):
                para.decompose()
            else:
                self.logger.error("Extra H2 (WD_SubjectLine) heading: %r %s", h2, pstate)

        if pstate.h1 and pstate.h2:
            return

        self.__handle_special_cases(base_url, pstate, table)

        if self.DEBUGGING and (not pstate.h1 or not pstate.h2):
            pdb.set_trace()

    def __handle_h1_special_cases(self, base_url: str, pstate: PageState, table: Tag) -> None:
        "Set H1 heading for special cases"
        # Only include the first 3 rows of the table
        # tr[0] page header boilerplate -- though a couple of pages incorrectly have headings here
        # tr[1] H1 headings (WD_ProgramName)
        # tr[2] H2 headings (WD_SubjectLine)
        top_rows = table.find_all("tr", recursive=False, limit=3)
        if len(_h1_paragraphs(top_rows)) == 0 and (h2s := _h2_paragraphs(top_rows)):
            # e.g., 44-211_552_Moving_Assistance_Program, 40-100_National_Voter_Registration_Act_-_Kick-Off
            # These misclassifies H1 heading as a WD_SubjectLine,
            # so there are multiple WD_SubjectLine and no WD_ProgramName
            # This logic needs to be run before the typical H1/H2 extraction,
            # which would remove use the first WD_SubjectLine as H2 when it should be H1
            assert not pstate.h1, f"Unexpected missing H1: {pstate}"
            first_para = h2s[0]
            pstate.h1 = to_markdown(first_para.get_text(), base_url)
            first_para.decompose()
            self.logger.info("Using first H2 for missing H1: %s", pstate.h1)

    def __handle_extra_h1(self, pstate: PageState, h2: str) -> bool:
        if pstate.filename in [
            "4_1_1__GROW_Transition_Age_Youth_Employment_Program.htm",
            "4_1_2_GROW_Youth_Employment_Program.htm",
            "63-407_Work_Registration.htm",
            "63-802_Restoration_of_Lost_Benefits.htm",
        ]:
            # These incorrectly have multiple WD_ProgramName and no WD_SubjectLine
            # so use WD_ProgramName in subsequent rows as H2 heading
            if not pstate.h2:
                pstate.h2 = h2
                self.logger.info("Using WD_ProgramName as H2: %s", pstate.h2)
                return True
        return False

    def __handle_extra_h2(self, pstate: PageState, h2: str) -> bool:
        # SSI_SSP_COLA/SSI_SSP_COLA.htm has multiple WD_SubjectLine in the same td
        # so merge them into a single H2
        if pstate.filename == "SSI_SSP_COLA.htm":
            assert pstate.h2, "Expected H2 to be set"
            pstate.h2 += " " + h2
            return True
        return False

    def __handle_special_cases(self, base_url: str, pstate: PageState, table: Tag) -> None:
        if pstate.filename == "2_3_Comprehensive_Intake_and_Employability_Assessment.htm":
            pstate.h2 = pstate.title
            self.logger.info("Missing H2; using title as H2: %s", pstate)
            return

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

        top_rows = table.find_all("tr", recursive=False, limit=3)
        if pstate.filename == "Organ_Transplant_AntiRejection_Medications.htm":
            # The H1 and H2 headings are in the first row, typicall ignored b/c
            # it shouldn't have heading text.
            # Plus it doesn't use WD_ProgramName and WD_SubjectLine
            paras = top_rows[0].find("td").find_all("p", recursive=False)
            set_headings_by_order(paras)
            return

        # 40-181_Processing_Redeterminations doesn't use WD_ProgramName or WD_SubjectLine
        # Residency_for_Out-of-State_Students doesn't use WD_SubjectLine
        # At this point, we can't rely on class annotations, just parse based on order of paragraphs
        # H1 and H2 headings are typically in the second row, so exclude the first row
        # to avoid including irrelevant page header paragraphs
        heading_rows = top_rows[1:]
        set_headings_by_order(_nonempty_paragraphs(heading_rows))

        for para in _nonempty_paragraphs(heading_rows):
            self.logger.error("Extra heading: %r", para.get_text())

    def _check_h2_validity(self, page_state: PageState) -> None:
        "Tries to log a warning if the H2 heading is significantly different from the page title"
        assert page_state.h2
        diffs = count_diffs(page_state.h2.casefold(), page_state.title.casefold())
        if diffs[0] / len(page_state.h2) > 0.5:
            if page_state.filename in [
                "SSI_SSP_COLA.htm",
                "ABLE_and_CalABLE_Accounts_in_the_CalFresh_Program.htm",
                "Documentation_of_Case_Records.htm",
                "WPCS_Provider_Payment_Processing.htm",
            ]:
                # These have been manually reviewed and are expected to have a different H2
                return

            self.logger.info("H2 is significantly different from the page title: %s", page_state)
            if not page_state.h2[0].isdigit() and len(page_state.h2) > 100:
                self.logger.warning("H2 heading may not be a heading: %s", page_state.h2)

    # endregion
    # region ============= Parse main body of web page

    def _headings_and_sections_to_markdown(self, row: Selector, base_url: str) -> str:
        "Convert a table row into a heading and associated section text"
        cols = row.xpath("./td")

        ### Special cases

        if len(cols) == 1:
            # Near the bottom of 69-202_1_Identification_of_Refugees.htm, the row becomes 1-column
            # because there's a div-wrapped table. The row should have been part of the previous row
            # Treat the single-column row as if it was the second column of a 2-column row
            return self.__section_to_markdown(base_url, cols[0].get(), heading_level=3)

        if len(cols) == 8:
            # Bottom of 63-900_Emergency_CalFresh_Assistance.htm is an extra table with 8 columns;
            # just render it as a table
            return to_markdown(row.get(), base_url)

        if len(cols) == 3:
            # 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm has erroneous 3rd column
            # Remove the empty 3rd column
            assert (
                not cols[2].xpath(".//text()").get().strip()
            ), f"Erroneous 3rd column has text: {cols[2].get()}"
            cols[2].remove()
            # Update and let the next code block handle the 2-column rows (Typical case)
            cols = row.xpath("./td")
            assert len(cols) == 2

        ### Typical case

        if len(cols) == 2:
            md_texts = []
            # Use first column as a subheading
            raw_texts = cols[0].xpath(".//text()").getall()
            md_str = to_markdown(" ".join(raw_texts), base_url)
            if md_str:
                subheading_md = "### " + md_str
                # Check for WD_SectionHeading class in the first column
                paras = cols[0].xpath("./p")
                if not [para.attrib["class"] == "WD_SectionHeading" for para in paras]:
                    # minor inconsistency; mitigation: assume first column is a subheading
                    self.logger.info(
                        "Assuming subheading (despite lack of WD_SectionHeading): %s", subheading_md
                    )
                md_texts.append(subheading_md)

            # Use second column as the section text under the subheading
            section_md = self.__section_to_markdown(base_url, cols[1].get(), heading_level=3)
            md_texts.append(section_md)
            return "\n\n".join(md_texts)

        raise NotImplementedError(f"Unexpected number of columns in row: {len(cols)}: {row.get()}")

    def __section_to_markdown(self, base_url: str, html: str, heading_level: int) -> str:
        "Convert a table cell `td` (representing a heading section) into a markdown text"
        # To simplify parsing, remove extraneous whitespace to reduce BeautifulSoup elements
        # Join with a space; otherwise spaces around <span> text disappear causing words to join in markdown
        min_html = " ".join(line.strip() for line in html.split("\n"))
        soup = BeautifulSoup(min_html, "html.parser")

        # Use soup to convert the table cell into a div
        body = soup.find("td")
        body.name = "div"
        self.__fix_body(heading_level, soup, body)
        return to_markdown(str(soup), base_url)

    def __fix_body(
        self, heading_level: int, soup: BeautifulSoup, body: Tag | NavigableString
    ) -> None:
        "Convert any tags so they can be appropriately converted to markdown"
        state = HtmlListState(soup)
        # Iterate over a copy of body.contents since we may modify body.contents
        for child in list(body.contents):
            # if (
            #     child.name == "div"
            #     and len(child.contents) == 1
            #     and child.contents[0].name in ["table", "p"]
            # ):
            #     # For divs with only one child, ignore the div and process the child
            #     # Occurs for a table that is wrapped in a div for centering
            #     child = child.contents[0]
            #     # pdb.set_trace()

            if child.name == "p":
                # Convert lists presented as paragraphs into actual lists
                self.__convert_any_paragraph_lists(state, child)

                # Remove blank paragraphs AFTER __convert_any_paragraph_lists() in case they're blank WD_ListParagraphCxSpFirst
                if child.get_text().strip() == "":
                    child.decompose()
                    continue

            elif child.name == "div":
                # 63-405_Citizenship_or_Eligible_Non-Citizen_Status.htm has a div wrapping several <p> tags
                self.logger.info(
                    "div wrapping %i tags: %r",
                    len(child.contents),
                    [c.name for c in child.contents],
                )
                # Recursively process the div's children
                self.__fix_body(heading_level, soup, child)
            elif child.name == "table":
                table = child
                if self.__table_uses_rowspan(table):
                    # 69-202_1_Identification_of_Refugees.htm
                    self.__table_to_raw_text(table)
                    continue

                col_sizes = self.__size_of_columns(table)
                if len(col_sizes) == 1:
                    # bottom of 63-503_49_Sponsored_Noncitizen.htm has a 1-column table
                    # Convert the table to a body content
                    table.name = "div"
                    for tr in table.find_all("tr", recursive=False):
                        tr.name = "p"
                        tr.td.name = "span"
                    continue

                # 40-105_40_Immunizations.htm: first row of table is acting as a heading
                # 46-102_Single_Adult_Model.htm: has middle rows are acting as headings
                # Split table into separate tables
                tables = [table]
                for row in table.find_all("tr", recursive=False):
                    row_texts = [
                        td.get_text() for td in row.find_all(["td", "th"], recursive=False)
                    ]
                    # self.logger.warning("row_texts: %r", first_row_texts)
                    # cols = row1.find_all(["td", "th"], recursive=False)
                    # if "SECONDARY HEAVY USER CRITERIA" in row_texts[0].strip():
                    #     pdb.set_trace()
                    if len(row_texts) == 1:
                        if heading_level < 6:
                            row.name = f"h{heading_level + 1}"
                        else:
                            row.name = "p"  # use <p> tag for deep headings
                        for c in row.find_all(["p", "td"]):
                            c.name = "span"
                        tables[-1].insert_after(row)
                        table = soup.new_tag("table")
                        row.insert_after(table)
                        tables.append(table)
                    else:
                        table.append(row)
                if not tables[0].get_text().strip():
                    tables.remove(tables[0])
                if len(tables) > 1:
                    self.logger.info("Split table into %i tables", len(tables))

                for table in tables:
                    target_type = self.__table_conversion_type(table)
                    if target_type == TargetElementType.LIST:
                        self.__convert_table_to_list(soup, table)
                    elif target_type == TargetElementType.SECTIONS:
                        self.__convert_table_to_subsections(soup, table, heading_level)
                    elif target_type == TargetElementType.BODY:
                        pdb.set_trace()
                    elif target_type == TargetElementType.RAW_TEXT:
                        self.__table_to_raw_text(table)
                    else:
                        ...
            elif isinstance(child, NavigableString) or child.name in ["ul", "ol"]:
                pass
            elif child.get_text().strip() == "":
                pass
            else:
                raise NotImplementedError(f"Unexpected {child.name}: {child}")

    def __table_to_raw_text(self, table: Tag) -> None:
        if not (stripped_table_text := table.get_text().strip()):
            table.decompose()
            return

        self.logger.info(
            "Extracting text from complex or ill-formed table: %s", stripped_table_text
        )
        # TODO: Handle some of these cases
        table.name = "div"
        for row in table.find_all("tr", recursive=False):
            row.name = "p"
            row.string = row.get_text()

    def __convert_any_paragraph_lists(self, state: HtmlListState, para: Tag) -> None:
        if "class" not in para.attrs:
            return

        # WD_ListParagraphCxSpFirst,Middle,Last is used for unordered lists
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
            if (stripped_text := para.get_text().strip()) == "":
                # Remove blank list items
                para.decompose()
                return

            para.name = "li"
            # In 44-350_Overpayments, a table is erroneously interleaved with the list;
            # the table start with a WD_ListParagraphCxSpMiddle and ends with WD_ListParagraphCxSpLast
            if state.current_list is None:
                # In CalFresh/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm
                # incorrectly uses a mix of both in the same list
                self.logger.warning(
                    "Improperly annotated list item! Creating a new list for %r", stripped_text
                )
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

        # WD_ListParagraph is used for ordered lists
        # 63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm
        # incorrectly uses a mix of both WD_ListParagraph and WD_ListParagraphCxSp* in the same list
        if "WD_ListParagraph" in para["class"]:
            if state.current_list is None:
                # Use `ul` tag rather than `ol` since we'll leave the explicit numbering as is
                state.current_list = state.soup.new_tag("ul")

    def __table_conversion_type(self, table: Tag) -> TargetElementType:
        # TODO: In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm
        # many occurrences of a list inappropriately wrapped in a table and is rendered as a curious table in markdown
        col_sizes = self.__size_of_columns(table)

        if len(col_sizes) == 0:
            if stripped_text := table.get_text().strip():
                raise NotImplementedError(f"Unexpected 0-column table with text: {stripped_text}")
            else:
                table.decompose()
                return TargetElementType.NONE

        if len(col_sizes) == 1:
            # 42-300_Time_Limit_Requirements.htm
            # FIXME: Is this used?
            return TargetElementType.BODY

        if len(col_sizes) == 2:
            # 42-431_2_Noncitizen_Status.htm, 43-109_Unrelated_Adult_Male.htm
            # If the first column is just bullets, then convert the 2-column table to a list
            col1_length = 0
            for row in table.find_all("tr", recursive=False):
                col1 = row.find(["td", "th"], recursive=False)
                size = len(col1.get_text().strip())
                col1_length = max(col1_length, size)
            # self.logger.warning(
            #     "------------------ %s %r %i", col1.get_text(), col_sizes, col1_length
            # )
            if col1_length <= 1:
                # 43-109_Unrelated_Adult_Male.htm uses a blank <ul> tag in the first column, so col1_length=0
                return TargetElementType.LIST

            # If second column has a table, then convert the table to sections
            for row in table.find_all("tr", recursive=False):
                cols = row.find_all("td", recursive=False)
                col2 = cols[1]
                if col2.find("table"):
                    # 42-200_Property.htm
                    return TargetElementType.SECTIONS

            # rows = table.find_all("tr", recursive=False)
            # rows_text = [[td.text for td in row.find_all(["td", "th"], recursive=False)] for row in rows]
            # if ' Education ' in rows_text[1][0]:
            #     pdb.set_trace()
            # rows_nonempty_text = [
            #     [
            #         td.text.strip()
            #         for td in row.find_all(["td", "th"], recursive=False)
            #         if td.text.strip()
            #     ]
            #     for row in table.find_all("tr")
            # ]
            # if any(
            #         text.startswith("Allowable Purpose") for texts in rows_nonempty_text for text in texts
            #     ):
            #         pdb.set_trace()

            # First column is usually short and often acts as a heading
            # If the second column is long, then convert the table
            if col_sizes[1] > 2:
                return TargetElementType.SECTIONS

        # 42-431_2_Noncitizen_Status.htm and CalWORKs/42-200_Property.htm
        # use a 3-column table to create a list and sublist
        rows_nonempty_text = [
            [
                td.text.strip()
                for td in row.find_all(["td", "th"], recursive=False)
                if td.text.strip()
            ]
            for row in table.find_all("tr")
        ]
        # If all rows start with a bullet character, then convert the table to a list
        # 42-200_Property.htm has a non-bulleted "Note:" as a list item
        # 44-211_561_Homeless_Case_Management_Program.htm uses digits instead of bullets
        if all(
            row_texts[0] in BULLETS
            or row_texts[0].startswith("Note:")
            or re.match(r"\d+\.", row_texts[0])
            for row_texts in rows_nonempty_text
        ):
            return TargetElementType.LIST

        if table.find("table"):
            # 44-211_561_Homeless_Case_Management_Program.htm has nested table
            self.logger.info(
                "Converting table to raw text: %s: %r", col_sizes, rows_nonempty_text[0]
            )
            return TargetElementType.RAW_TEXT

        self.logger.info("Leaving table as is: %s: %r", col_sizes, rows_nonempty_text[0])
        return TargetElementType.NONE

    def __table_uses_rowspan(self, table: Tag) -> bool:
        for row in table.find_all("tr", recursive=False):
            for cell in row.find_all(["td", "th"], recursive=False):
                if "rowspan" in cell.attrs and int(cell.attrs["rowspan"]) > 1:
                    return True
        return False

    def __size_of_columns(self, table: Tag) -> Sequence[int]:
        col_lengths: defaultdict[int, int] = defaultdict(int)
        for row in table.find_all("tr", recursive=False):
            for i, cell in enumerate(row.find_all(["td", "th"], recursive=False)):
                # TODO: Instead of text length, consider the number of tags
                # size = len(cell.get_text().strip())
                size = len([c for c in cell.contents if str(c).strip()])
                col_lengths[i] = max(col_lengths[i], size)
        return tuple(col_lengths.values())

    def __indent_level(self, texts: Sequence[str]) -> int:
        "Return 0 for a top-level list, 1 for a sublist, etc."
        for i, text in enumerate(texts):
            if text in BULLETS:
                return i
            # CalWORKs/42-200_Property.htm has a non-bulleted "Note:" as a list item
            if text.startswith("Note:"):
                return i  # The note should be treated as a sublist since it can be a note about the prior list item
            # 44-211_561_Homeless_Case_Management_Program.htm uses digits followed by "." instead of bullets
            # 610_SIP_Approval.htm has digits instead of bullets; its not obvious if the digits are meaningful
            # Just treat them as bullets
            if text.rstrip(".").isdigit():
                return i
            # if text != "":
            #     pdb.set_trace()
            assert text == "", f"Unexpected text before list bullet: {text!r}"
        raise ValueError("No bullet found in text list: {texts!r}")

    def __td_to_text(self, td: Tag) -> str:
        stripped_text = td.get_text().strip()
        # 42-405_Absence_from_California.htm uses an empty li tag to create a bullet
        # Unfortunately this is indistinguishable from an empty string when td.get_text().strip() is called
        # Since we need to distinguish between empty string and a bullet in __indent_level(),
        # we need to detect and handle this case.
        if stripped_text == "" and td.find("ul"):
            return "•"  # Use any character from BULLETS
        return stripped_text

    def __convert_table_to_list(self, soup: BeautifulSoup, table: Tag) -> None:
        table.name = "ul"
        rows = table.find_all("tr", recursive=False)
        curr_indent_level = 0
        ul = table
        ul_stack = [table]
        START_DEBUG = False
        for row in rows:
            row.name = "li"
            cols = row.find_all(["td", "th"], recursive=False)
            row_texts = [self.__td_to_text(td) for td in cols]
            indent_level = self.__indent_level(row_texts)

            # 42-431_2_Noncitizen_Status.htm and CalWORKs/42-200_Property.htm
            # use a single 3-column table to create a list and sublist
            if indent_level == curr_indent_level:
                pass
            elif indent_level == curr_indent_level + 1:
                ul = soup.new_tag("ul")
                ul_stack.append(ul)
                row.insert_before(ul)
                curr_indent_level = indent_level

            elif indent_level < curr_indent_level:
                while len(ul_stack) > indent_level + 1:
                    ul_stack.pop()
                ul = ul_stack[-1]
                curr_indent_level = indent_level
            else:
                raise NotImplementedError(
                    f"Unexpected indent level: {indent_level} vs {curr_indent_level}"
                )

            assert (
                len(ul_stack) == indent_level + 1
            ), f"Expected {indent_level + 1} stack size but got {len(ul_stack)}"

            if ul != table:
                ul.append(row)

            if indent_level != 0:
                for col in cols[:indent_level]:
                    col.decompose()
                cols = row.find_all(["td", "th"], recursive=False)
                row_texts = [td.text.strip() for td in cols]

            if START_DEBUG or any(
                text.strip().startswith("Allowable Purpose") for text in row_texts
            ):
                START_DEBUG = True
                # pdb.set_trace()

            prefix = ""
            stripped_text = cols[0].get_text().strip()
            # CalWORKs/42-200_Property.htm has a non-bulleted "Note:" as a list item
            if stripped_text.startswith("Note:"):
                content_col = cols[0]
            else:
                # 44-211_561_Homeless_Case_Management_Program.htm uses digits followed by "." instead of bullets
                # 610_SIP_Approval.htm has digits instead of bullets; its not obvious if the digits are meaningful
                # Just treat them as bullets
                if stripped_text.rstrip(".").isdigit():
                    prefix = stripped_text
                else:
                    assert (
                        stripped_text == "" or stripped_text in BULLETS
                    ), f"First column: {stripped_text!r}"
                # Remove bullet column
                cols[0].decompose()

                # 89-201_Minor_Parent.htm has a empty 3rd column
                # remove empty columns
                for col in row.find_all(["td", "th"], recursive=False):
                    if col.get_text().strip() == "":
                        col.decompose()
                cols = row.find_all(["td", "th"], recursive=False)

                row_texts = [td.text.strip() for td in cols]
                # if len(cols) != 1:
                #     pdb.set_trace()
                assert len(cols) == 1, f"Expected only 1 non-empty column but got: {row_texts!r}"
                content_col = cols[0]

            if prefix:
                if prefix[-1] not in [".", ":", ")"]:
                    # Add some delimiter to separate the prefix from the content
                    prefix += ":"
                content_col.insert_before(f"{prefix} ")
            content_col.name = "span"
            _remove_empty_elements(content_col.contents)
            if content_col.contents[0].name and content_col.contents[0].name in ["p"]:
                # to prevent line break immediately after bullet character
                content_col.contents[0].name = "span"

            # if any(text.strip().startswith("Home – applicant/participant leaves home due") for text in row_texts):
            #     pdb.set_trace()

            for child in content_col.contents:
                if child.name == "table":
                    # Handle nested tables acting as a sublist (42-431_2_Noncitizen_Status.htm)
                    target_type = self.__table_conversion_type(child)
                    if target_type == TargetElementType.LIST:
                        self.__convert_table_to_list(soup, child)
                    elif target_type == TargetElementType.RAW_TEXT:
                        self.__table_to_raw_text(child)
                elif child.name == "p":
                    # Replace <p> tags with <span> tags to keep content visually within the list item (42-200_Property.htm)
                    child.name = "span"
                    child.insert_before(soup.new_tag("br"))
                elif child.name in ["span", "p"]:
                    pass

    def __has_single_column_row(self, rows: list[Tag]) -> bool:
        for row in rows:
            cols = row.find_all(["td", "th"], recursive=False)
            if len(cols) == 1:
                return True
        return False

    def __convert_table_to_subsections(
        self, soup: BeautifulSoup, table: Tag, heading_level: int
    ) -> None:
        rows = table.find_all("tr", recursive=False)

        # Use first row as table headings if all cells are bold
        cols = rows[0].find_all(["td", "th"], recursive=False)

        # table_headings = [cell.get_text().strip() for cell in cols]
        # if table_headings[0] == "Allowable Purpose":
        #     pdb.set_trace()

        if len(cols) == 2 and self.__table_row_is_heading(cols):
            # Since all cells are bold, treat them as table headings
            table_headings = [cell.get_text().strip() for cell in cols]
            # self.logger.warning("table_headings: %r", table_headings)
            rows[0].decompose()
            rows = rows[1:]
        else:
            # Since all cells are not bold, assume they are not table headings
            table_headings = ["" for _ in range(2)]

        has_single_column_row = self.__has_single_column_row(rows)

        # if table_headings[0] == "Allowable Purpose":
        #     pdb.set_trace()

        for row in rows:
            cols = row.find_all(["td", "th"], recursive=False)
            if len(cols) == 1:
                # Treat single column rows as a heading
                row.name = "span"
                row.attrs = {}  # remove any attributes to clear clutter
                cols[0].name = f"h{heading_level + 1}"
            elif len(cols) == 2:
                # if row.get_text().strip().startswith("Qualified noncitizens who entered on or after August 22, 1996"):
                #     pdb.set_trace()
                # Treat 2-column rows as a subheading and its associated body
                row.name = "div"
                row.attrs = {}

                # Use first column as a subheading
                curr_heading_level = (
                    heading_level + 2 if has_single_column_row else heading_level + 1
                )
                cols[0].name = f"h{curr_heading_level}"
                cols[0].attrs = {}

                # Handle multiple lines in the first column (42-431_2_Noncitizen_Status.htm: "Qualified noncitizens who ...")
                splits = split_block_tags(cols[0])
                col1_remainder = soup.new_tag("div")
                for split in splits[2:]:
                    for s in split:
                        col1_remainder.append(s)
                self.__fix_body(curr_heading_level, soup, col1_remainder)
                cols[0].insert_after(col1_remainder)

                for child in cols[0].contents:
                    if child.name:
                        child.name = "span"  # to prevent line break
                if table_headings[0]:
                    if cols[0].contents[0].name:
                        cols[0].contents[0].name = "span"  # to prevent line break
                    cols[0].contents[0].insert_before(f"{table_headings[0]}: ")

                # Use second column as the section text under the subheading
                cols[1].name = "div"
                cols[1].attrs = {}
                self.__fix_body(curr_heading_level, soup, cols[1])
                if table_headings[1]:
                    if cols[1].contents[0].name:
                        cols[1].contents[0].name = "span"  # to prevent line break
                    cols[1].contents[0].insert_before(f"{table_headings[1]}: ")
            else:
                raise NotImplementedError(f"Too many columns in row: {len(cols)}: {cols.strings}")

        table.name = "span"
        table.attrs = {}
        # pdb.set_trace()

    def __table_row_is_heading(self, first_row_cols: Sequence[Tag]) -> bool:
        # If all columns are bold, then treat the row as a heading
        if all(cell.find_all("b") for cell in first_row_cols):
            # unless there is a table in any cell, then it's not a heading (42-431_2_Noncitizen_Status.htm)
            if not any(cell.find_all("table") for cell in first_row_cols):
                return True

        # If all columns have a p tag using WD_TableHeading class, then treat the row as a heading
        if [
            cell
            for cell in first_row_cols
            if cell.find_all("p", attrs={"class": "WD_TableHeading"})
        ] == first_row_cols:
            return True
        return False


# endregion
# region ============= BeautifulSoup helper functions


def _h1_paragraphs(rows: list[Tag]) -> Sequence[Tag]:
    return __flatten_and_filter_out_blank(
        rows, lambda row: row.find_all("p", class_="WD_ProgramName")
    )


def _h2_paragraphs(rows: list[Tag]) -> Sequence[Tag]:
    return __flatten_and_filter_out_blank(
        rows, lambda row: row.find_all("p", class_="WD_SubjectLine")
    )


def _nonempty_paragraphs(rows: list[Tag]) -> Sequence[Tag]:
    return __flatten_and_filter_out_blank(rows, lambda row: row.find_all("p"))


def _remove_empty_elements(contents: list[Tag]) -> None:
    # Iterate over a copy of contents since list will be modified, esp. when contents is Tag.contents
    for c in list(contents):
        stripped_text = c.get_text().strip()
        if stripped_text in [""]:
            if isinstance(c, NavigableString):
                # for NavigableString (raw text) which doesn't have decompose()
                c.extract()
            else:
                c.decompose()


def __flatten_and_filter_out_blank(rows: list[Tag], resultset_generator: Callable) -> Sequence[Tag]:
    return [
        para
        for para in chain(*[resultset_generator(row) for row in rows])
        if para.get_text().strip()
    ]


def _hyperlinked_paragraphs(tag: Tag) -> Sequence[Tag]:
    return [
        span.parent
        for span in tag.find_all("span", class_="WD_Hyperlink")
        if span.parent.get_text().strip()
    ]


TYPICAL_TOC_LINKS = {
    "Purpose",
    "Policy",
    "Background",
    "Definition",
    "Requirements",
    "Verification Docs",
}


def split_block_tags(tag: Tag) -> list[list[Tag]]:
    "Split block-level tags into separate tags for each line"
    splits = []
    curr_split: list[PageElement] = []
    for c in tag.contents:
        if c.name in ["p", "div", "table"]:
            if curr_split:
                splits.append(curr_split)
            curr_split = [c]
        else:
            curr_split.append(c)
    if curr_split:
        splits.append(curr_split)
    return splits


# endregion


def to_markdown(html: str, base_url: Optional[str] = None) -> str:
    h2t = html2text.HTML2Text()

    # Refer to https://github.com/Alir3z4/html2text/blob/master/docs/usage.md and html2text.config
    # for options:
    # 0 for no wrapping
    h2t.body_width = 0
    h2t.wrap_links = False

    if base_url:
        h2t.baseurl = base_url
    # TODO: Enable and test, if this is desired
    # h.skip_internal_links = False

    # wrap 'pre' blocks with [code]...[/code] tags
    h2t.mark_code = True
    # Include the <sup> and <sub> tags
    h2t.include_sup_sub = True

    markdown = h2t.handle(html)
    # Remove headings with only a bullet, such as 42-431_2_Noncitizen_Status.htm
    # markdown = re.sub("^#####  ·\n\n", "- ", markdown, flags=re.MULTILINE)

    # Remove the bullet before list items prefixed with a number/letter and dot/')'
    # (eg, 41-400_Deprivation.htm, Coverage_for_Immigrants.htm)
    # because this causes markdown_tree (i.e., mistletoe) to treat a single list item
    # as an unordered list item with a nested ordered sublist item
    markdown = re.sub(r"^( *)[\*|\-|\+] (\w{1,2}+[\.|\)] )", r"\1\2", markdown, flags=re.MULTILINE)

    # Pickle_Program.htm produces "~~~~" which gets interpreted as a code block when chunking
    markdown = markdown.replace("~~~~", "")

    # 63-503_41_Self-Employment_Income.htm produces "---" after a 1-column,1-row table
    # Remove "---" lines, which causes the previous line to be interpreted as a heading
    markdown = re.sub(r"^\-\-\- *\n", "", markdown, flags=re.MULTILINE)

    return markdown.strip()

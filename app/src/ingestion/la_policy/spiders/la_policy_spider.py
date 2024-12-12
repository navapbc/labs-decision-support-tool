import os
import pdb
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import scrapy
import html5lib
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from markdownify import markdownify
from scrapy.http import HtmlResponse
from scrapy.selector import SelectorList, Selector

app_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
print("Adding app folder to sys.path:", app_folder)
sys.path.append(app_folder)
from src.util import string_utils  # noqa: E402
from src.util.string_utils import count_diffs


@dataclass
class ScrapingState:
    soup: BeautifulSoup
    current_list: Optional[Any] = None


@dataclass
class PageState:
    title: str
    title_diff_logged: bool = False
    h1: Optional[str] = None
    h2: Optional[str] = None


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
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-504_ESAP_Waiver_for_Elderly_and_Disabled_Households/63-504_ESAP_Waiver_for_Elderly_and_Disabled_Households.htm"

            # "Cannot insert None into a tag."
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions/63-410_3_Able-Bodied_Adults_Without_Dependents_Exemptions.htm"
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CAPI/CAPI/49-015_CAPI_Application_Process/49-015_CAPI_Application_Process.htm"
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/44-211_552_Moving_Assistance_Program/44-211_552_Moving_Assistance_Program.htm"
            # NotImplementedError: Unexpected number of columns in row: 3
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members/40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm"

            # Expected one paragraph in heading row: <tr>
            "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/SSI_SSP_COLA/SSI_SSP_COLA.htm"

            # page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/40-181_Processing_Redeterminations/40-181_Processing_Redeterminations.htm"
            # page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-402_6_Authorized_Representative/63-402_6_Authorized_Representative.htm"
            # page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/69-202_1_Identification_of_Refugees/69-202_1_Identification_of_Refugees.htm"
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Organ_Transplant_AntiRejection_Medications/Organ_Transplant_AntiRejection_Medications.htm"
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalWORKs/CalWORKs/70-100_Trafficking_And_Crime_Victims_Assistance_Program/70-100_Trafficking_And_Crime_Victims_Assistance_Program.htm"
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/Medi-Cal/Medi-Cal/Pickle_Program/Pickle_Program.htm"
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GROW/GROW/4_1_2_GROW_Youth_Employment_Program/4_1_2_GROW_Youth_Employment_Program.htm"

            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/CalFresh/CalFresh/63-405_Citizenship_or_Eligible_Non-Citizen_Status/63-405_Citizenship_or_Eligible_Non-Citizen_Status.htm"
            page_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/GR/GR/40-101_19_Extended_Foster_Care_Benefits/40-101_19_Extended_Foster_Care_Benefits.htm"

    # FIXME: 40-101_19_Extended_Foster_Care_Benefits.htm.md, 1210_Overview.htm are missing spaces: "*Whatchanged*?" "Thebrochure"

            yield response.follow(page_url, callback=self.parse_page)
        else:
            lis = response.css("li.book")
            for li in lis[2:]:  # Start with "Programs"-related pages. TODO: Remove slice
                href = li.css("a::attr(href)").get()
                if href != "#":
                    page_url = f"{self.common_url_prefix}/{href}"
                    # self.logger.info("Found page URL %s", page_url)
                    yield response.follow(page_url, callback=self.parse_page)

    # Return value is saved to filename set by scrape_la_policy.OUTPUT_JSON
    def parse_page(self, response: HtmlResponse) -> dict[str, str]:
        self.logger.info("parse_page %s", response.url)
        extractions = {"url": response.url}

        # Save html file for debugging
        filepath = "./scraped/" + response.url.removeprefix(
            self.common_url_prefix + "/mergedProjects/"
        )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # soup = BeautifulSoup(response.body.decode("utf-8").replace("\r\n", ""), "html5lib")
        # html = soup.prettify()
        Path(filepath).write_bytes(response.body)
        # Path(filepath).write_text(html, encoding="utf-8")
        # mresponse = Selector(text=html)

        tables = response.xpath("body/table")
        rows = tables[0].xpath("./tr")

        # assert len(tables) == 1, "Expected one top-level table"
        # FIXME: 63-407_Work_Registration.htm has a table that is outside the top-level table
        # FIXME: In Organ_Transplant_AntiRejection_Medications.htm and Pickle_Program.htm, the H1 and H2 are in the ignored first row
        #     and not classed as WD_ProgramName and WD_SubjectLine
        if response.url.endswith("63-407_Work_Registration.htm") or response.url.endswith("Organ_Transplant_AntiRejection_Medications.htm") or response.url.endswith("Pickle_Program.htm"):
            extractions["title"] = "SKIPPED"
            return extractions

        header_md = to_markdown(rows[0].get())
        assert (
            "Purpose" in header_md and "Policy" in header_md
        ), "Expected 'Purpose' and 'Policy' in first row (which acts as page header)"
        # Ignore the first row, which is the page header boilerplate
        # TODO: Extract "Release Date" value
        rows = rows[1:]

        # Convert table rows into headings and associated sections
        page_state = PageState(title=response.xpath("head/title/text()").get().strip())
        md_list: list[str] = [
            self._convert_to_headings_and_sections(row, self.common_url_prefix, page_state)
            for row in rows
        ]

        markdown = "\n\n".join(md_list)
        Path(f"{filepath}.md").write_text(
            f"[Source page]({response.url})\n\n" + markdown, encoding="utf-8"
        )

        assert page_state.h1, f"Missing H1: {page_state}"
        assert page_state.h2, f"Missing H2: {page_state}"
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
            "GAIN", "GAIN/GROW",
            "GR", "GENERAL RELIEF",
            "GROW",
            "IHSS", "IN-HOME SUPPORTIVE SERVICES", "IN-HOME SUPPORTIVE SERVICES PROGRAM",
            "Medi-Cal", "MEDI-CAL PROGRAM",
            "REP", "REFUGEE EMPLOYMENT PROGRAM",
        ]
    }

    def _convert_to_headings_and_sections(
        self, row: Selector, base_url: str, page_state: PageState
    ) -> str:
        # FIXME: Record sentences and ensure they exist in the output markdown
        tds = row.xpath("./td")
        heading_md = []
        h1s = tds.xpath(".//p[@class='WD_ProgramName']")
        h2s = tds.xpath(".//p[@class='WD_SubjectLine']")
        # pdb.set_trace()
        if not page_state.h1 and len(h1s):
            if len(h2s):
                for para in h1s:
                    page_state.h1 = to_markdown(self._parse_heading(para), base_url)
                    heading_md.append("# " + page_state.h1)
                return "\n".join(heading_md)
            else:
                # For 4_1_1__GROW_Transition_Age_Youth_Employment_Program.htm, 4_1_2_GROW_Youth_Employment_Program.htm,
                # they incorrectly have multiple WD_ProgramName and no WD_SubjectLine
                # so use WD_ProgramName in subsequent rows as H2.
                for para in h1s:
                    parsed_heading_md = to_markdown(self._parse_heading(para), base_url)
                    if not page_state.h1:
                        page_state.h1 = parsed_heading_md
                        heading_md.append("# " + parsed_heading_md)
                        continue
                    if not page_state.h2:
                        page_state.h2 = parsed_heading_md
                        heading_md.append("## " + parsed_heading_md)
                        continue
                    self.logger.error("Extra heading: %r %s", parsed_heading_md, page_state)
                return "\n".join(heading_md)

        # 44-211_552_Moving_Assistance_Program.htm misclassifies WD_ProgramName as a WD_SubjectLine,
        # so check for H1 before H2
        # 69-202_1_Identification_of_Refugees incorrectly uses WD_SubjectLine class for non-heading text
        # so ignore it if page_state.h2 is already set
        if page_state.h1 and not page_state.h2 and len(h2s):
            for para in h2s:
                # FIXME: change h1 and h2 to list or boolean
                page_state.h2 = to_markdown(self._parse_heading(para), base_url)
                heading_md.append("## " + page_state.h2)
            return "\n".join(heading_md)

        if not page_state.h1 or not page_state.h2:
            if (texts := tds.xpath(".//text()").getall()) and "".join(
                [text.strip() for text in texts]
            ):
                # 40-181_Processing_Redeterminations.htm
                # does not use the typical WD_ProgramName and WD_SubjectLine classes to identify H1 and H2 headings
                paras = [p for p in tds.xpath("./p") if p.xpath(".//text()").get().strip()]
                if len(paras) > 1:
                    # One page used multiple consecutive <p> tags to split up a single heading title
                    # For several other pages, this is a sign of a missing H1 or H2 heading
                    self.logger.info("Expected only one <p> for H1/H2 heading: %s", texts)
                if set(texts) & self.TYPICAL_SUBHEADINGS:
                    if page_state.title == "2_3_Comprehensive Intake and Employability Assessment":
                        page_state.h2 = page_state.title
                        self.logger.info("Missing H2; using title as H2: %s", page_state)
                    else:
                        self.logger.error("Did not find expected H1 or H2 headings: %s", page_state)
                else:
                    if page_state.h1 is None:
                        for para in paras:
                            h1 = to_markdown(self._parse_heading(para), base_url)
                            page_state.h1 = h1
                            heading_md.append("# " + h1)
                    elif page_state.h2 is None:
                        for para in paras:
                            # Some `p` tags don't have the `WD_SubjectLine` class when it should
                            h2 = to_markdown(self._parse_heading(para), base_url)
                            page_state.h2 = h2
                            heading_md.append("## " + h2)
                    else:
                        for para in paras:
                            assumed_heading = "## " + to_markdown(
                                self._parse_heading(para), base_url
                            )
                            # FIXME: Usually incorrect assumption
                            self.logger.error("Assuming H2 heading: %r", assumed_heading)
                            heading_md.append(assumed_heading)
                    return "\n".join(heading_md)

        assert page_state.h1 and page_state.h2, f"Expecting H1 and H2 to be set: {page_state}"

        if (
            not page_state.title_diff_logged
            and (page_state.h2.casefold() not in page_state.title.casefold())
            and (page_state.title.casefold() not in page_state.h2.casefold())
            and (
                count_diffs(page_state.h2.casefold(), page_state.title.casefold())
                / len(page_state.title)
                > 0.7
            )
        ):
            page_state.title_diff_logged = True
            self.logger.info(
                "Expected H2 is significantly different from the page title: %s", page_state
            )

            if not page_state.h2[0].isdigit() and len(page_state.h2) > 100:
                self.logger.warning("H2 heading may not be a heading: %s", page_state.h2)

        if len(tds) == 1:
            # Near the bottom of 69-202_1_Identification_of_Refugees.htm, the row becomes 1-column
            # because there's a div-wrapped table. The row should have been part of the previous row.
            # Treat the single-column row as if it was the second column of a 2-column row
            return self._parse_section(base_url, tds[0].get(), heading_level=3)

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
            if not next(para.attrib["class"] == "WD_SectionHeading" for para in paras):
                # minor inconsistency; mitigation: assume first column is a subheading
                self.logger.debug(
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

    def _parse_section(self, base_url, html: str, heading_level: int) -> str:
        # Remove extraneous whitespace to simplify parsing
        min_html = "".join(line.strip() for line in html.split("\n")) #.replace("\r\n", "\n")
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

    def __fix_body(self, heading_level: int, soup, body: Tag | NavigableString):
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
            else:
                raise NotImplementedError(f"Unexpected {child.name}: {child}")

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
        # row_text = [td.text for td in table.find("tr").find_all(["td", "th"], recursive=False)]
        # self.logger.debug("_should_convert_table: %r", row_text)

        if self._table_uses_rowspan(table):
            row_text = [td.text for td in table.find("tr").find_all(["td", "th"], recursive=False)]
            # 69-202_1_Identification_of_Refugees.htm
            self.logger.info("Leaving table using rowspan as is: %s", row_text)
            return False

        # FIXME: In 40-103_44__Medi-Cal_For_CalWORKs_Ineligible_Members.htm
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
    def _convert_table_to_sections(self, state: ScrapingState, table: Tag, heading_level: int):
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
    markdown = re.sub(r'\s\s+', ' ', markdown)
    # r"[\n\r]\n+"

    if base_url:
        # Replace non-absolute URLs with absolute URLs
        markdown = string_utils.resolve_urls(base_url, markdown)
    return markdown.strip()

import copy
import re
from dataclasses import dataclass, field


@dataclass
class PageInfo:
    # Current page number
    pageno: int

    # Title of the PDF document shown in the header
    doc_title: str

    # Page number in the PDF header on each page
    doc_pageno: str = ""
    # Title in the PDF header on each page
    header_title: str = ""
    # BEM section in the PDF header on each page
    bem_section: str = ""
    # Date in the PDF header on each page
    text_date: str = ""

    def parse_header_item(self, text: str) -> str | None:
        "Returns the type of header item that was parsed"
        text = text.strip()
        if title := parse_title(text, self.doc_title):
            self.header_title = title
            return "title"
        if bem_section := parse_bem_section(text):
            self.bem_section = bem_section
            return "bem_section"
        if doc_pageno := parse_doc_pageno(text):
            self.doc_pageno = doc_pageno
            return "doc_pageno"
        if text_date := parse_date(text):
            self.text_date = text_date
            return "date"
        return None


PAGENO_REGEX = re.compile("^([0-9]+) of ([0-9]+)$")
HEADER_DATE_REGEX = re.compile("([0-9]+-[0-9]+-[0-9]+)")
BEM_SECTION_REGEX = re.compile("^BEM ([0-9]+)$")


def parse_doc_pageno(text: str) -> str | None:
    matches = PAGENO_REGEX.match(text)
    if matches:
        assert len(matches.groups()) == 2
        return matches.groups()[0]
    return None


def parse_date(text: str) -> str | None:
    matches = HEADER_DATE_REGEX.search(text)
    if matches:
        assert len(matches.groups()) == 1
        return matches.groups()[0]
    return None


def parse_bem_section(text: str) -> str | None:
    matches = BEM_SECTION_REGEX.match(text)
    if matches:
        assert len(matches.groups()) == 1
        return matches.groups()[0]
    return None


def parse_title(text: str, doc_title: str) -> str | None:
    if text.casefold() == doc_title.casefold():
        return text
    return None


@dataclass
class Heading:
    title: str
    level: int
    pageno: int | None


@dataclass
class ParsingContext:
    # Used to find headings in the PDF
    heading_stack: list[Heading]

    # The headings for the current text
    parent_headings: list[Heading] = field(default_factory=list)

    # The page information for the current text
    page_info: PageInfo = field(default_factory=lambda: PageInfo(0, ""))

    # Paragraph number of the current text starting from 1 after each heading
    parano: int = 0

    # Tags collected from bolded words in the text
    # Each list of tags corresponds to a heading level for the current text
    tags: list[list[str]] = field(default_factory=list)

    def is_next_heading(self, text: str) -> Heading | None:
        if not self.heading_stack:
            return None

        next_heading = self.heading_stack[-1]
        # Use casefold() to make case-insensitive comparison
        if text.casefold() == next_heading.title.casefold():
            return next_heading
        return None

    def set_next_heading(self) -> None:
        next_heading = self.heading_stack.pop()
        level = next_heading.level

        # Update the parent_headings list with the new heading
        if level > len(self.parent_headings):  # new subheading
            self.parent_headings.append(next_heading)
            self.tags.append([])
        else:
            # Pop all subheadings (if any) until we reach level
            while level < len(self.parent_headings):
                self.parent_headings.pop()
                self.tags.pop()

            # Then set the current heading
            self.parent_headings[-1] = next_heading
            self.tags[-1] = []

        assert level == len(self.parent_headings)
        # Reset the paragraph number
        self.parano = 0


@dataclass
class AnnotatedText:
    parano: int
    text: str
    bolded: bool
    span: bool
    page: PageInfo
    headings: list[Heading]
    tags: list[str]

    def __init__(self, pc: ParsingContext, tagname: str, text: str):
        self.parano = pc.parano
        self.text = text
        self.bolded = tagname == "BOLD"
        self.span = tagname == "Span"
        self.page = copy.deepcopy(pc.page_info)
        self.headings = pc.parent_headings.copy()
        self.tags = pc.tags[-1].copy()

    def __str__(self) -> str:
        return f"{self.page.pageno}.{self.parano} {self.bolded} {self.headings[-1].level}:{self.headings[-1].title} [{self.tags}] {self.text}"

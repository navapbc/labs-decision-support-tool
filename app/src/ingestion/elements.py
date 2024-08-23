from dataclasses import dataclass
from enum import Enum
from typing import List


class TextType(Enum):
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    LIST = "List"


@dataclass
class Page:
    # The actual page in the document
    pdf_page_number: int

    # The label of the page in the document
    # E.g., "i", "ii", "1", "2", etc.
    document_page_number: str


@dataclass
class Heading:
    title: str
    level: int
    page: Page


@dataclass
class EnrichedText:
    text: str
    type: TextType
    headings: List[Heading]
    page: Page

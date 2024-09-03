from dataclasses import dataclass
from enum import StrEnum
from typing import List

from src.ingestion.pdf_stylings import Styling
from src.util.pdf_utils import Heading


class TextType(StrEnum):
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    LIST = "List"


@dataclass
class Link:
    start_index: int
    text: str
    url: str


@dataclass
class EnrichedText:
    text: str
    type: TextType
    headings: List[Heading]
    page_number: int | None = None
    id: str | None = None
    stylings: List[Styling] | None = None
    links: List[Link] | None = None

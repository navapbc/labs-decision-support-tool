from dataclasses import dataclass
from enum import StrEnum
from typing import List

from src.util.pdf_utils import Heading


class TextType(StrEnum):
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    LIST = "List"
    # For Title elements that cannot be found as a heading in the outline
    TITLE = "Title"


@dataclass
class Styling:
    # The text with the style
    text: str
    # Page number where the styled text is located
    pageno: int
    # Nested parent headings where the styled text is located
    headings: List[Heading]
    # Other text before and after the styled text
    wider_text: str
    # Style attributes
    bold: bool = False


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

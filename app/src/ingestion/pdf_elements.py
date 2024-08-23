from dataclasses import dataclass
from enum import Enum
from typing import List


class TextType(Enum):
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    LIST = "List"


@dataclass
class Heading:
    title: str
    level: int
    page_number: int | None = None


@dataclass
class EnrichedText:
    text: str
    type: TextType
    headings: List[Heading]
    page_number: int | None = None

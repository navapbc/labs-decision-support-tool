from dataclasses import dataclass
from enum import Enum
from typing import List

from src.util.pdf_utils import Heading


class TextType(Enum):
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    LIST = "List"


@dataclass
class EnrichedText:
    text: str
    type: TextType
    headings: List[Heading]
    page_number: int | None = None
    id: str | None = None

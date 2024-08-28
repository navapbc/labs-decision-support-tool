import logging

from src.ingestion.pdf_elements import EnrichedText, TextType
from src.ingestion.pdf_stylings import Styling

logger = logging.getLogger(__name__)


def associate_stylings(
    enriched_texts: list[EnrichedText], stylings: list[Styling]
) -> list[EnrichedText]:
    "Given EnrichedTexts and Stylings, assocate stylings to the corresponding text item"
    for e_text in enriched_texts:
        print("-------")
        e_text.stylings = [styling for styling in stylings if styling_matches_text(styling, e_text)]
    return enriched_texts


def styling_matches_text(styling: Styling, e_text: EnrichedText) -> bool:
    stripped_wider_text = styling.wider_text.replace("• ", "").strip()
    print("S: ", styling.wider_text.replace("• ", ""))
    print("T: ", e_text.text)
    print(stripped_wider_text in e_text.text.strip())
    print(abs(len(stripped_wider_text) - len(e_text.text.strip()))<10)
    return (
        styling.pageno == e_text.page_number
        and styling.headings == e_text.headings
        and stripped_wider_text in e_text.text.strip()
        and abs(len(stripped_wider_text) - len(e_text.text.strip()))<10
    )


def apply_stylings(enriched_texts: list[EnrichedText]) -> list[EnrichedText]:
    """
    Given EnrichedTexts, apply stylings to the text in markdown format.
    """
    return enriched_texts


def add_markdown(enriched_texts: list[EnrichedText]) -> list[EnrichedText]:
    for enriched_text in enriched_texts:
        # Note that the links and stylings should be applied [TASK 2.a and 2.b] to the text before
        # the "    - " is prepended to ListItem elements so that positional data like
        # link.start_index can be used without having to account for text transformations.

        if enriched_text.type == TextType.LIST_ITEM:
            enriched_text.text = "    - " + enriched_text.text
    return enriched_texts


def _should_merge_list_text(text: EnrichedText, next_text: EnrichedText) -> bool:
    if text.headings != next_text.headings:
        return False

    if next_text.type != TextType.LIST_ITEM:
        return False

    if text.type in [TextType.LIST_ITEM, TextType.LIST]:
        return True

    return text.type == TextType.NARRATIVE_TEXT and text.text.rstrip().endswith(":")


def group_texts(markdown_texts: list[EnrichedText]) -> list[EnrichedText]:
    """
    Given EnrichedTexts, concatenate list tems together
    with each other and with the preceeding NarrativeText.
    """

    if not markdown_texts:
        return []

    grouped_texts = [markdown_texts[0]]

    for current_text in markdown_texts[1:]:
        previous_text = grouped_texts[-1]

        if _should_merge_list_text(previous_text, current_text):
            # Append the current text to the previous one
            previous_text.text += "\n" + current_text.text
            previous_text.type = TextType.LIST
        else:
            # If it's not merged, just add it as a new element
            grouped_texts.append(current_text)

    return grouped_texts

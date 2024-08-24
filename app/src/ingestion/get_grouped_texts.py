import logging

from src.ingestion.pdf_elements import EnrichedText, TextType

logger = logging.getLogger(__name__)


def should_merge_list_text(text: EnrichedText, next_text: EnrichedText) -> bool:
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

        if should_merge_list_text(previous_text, current_text):
            # Append the current text to the previous one
            previous_text.text += "\n" + current_text.text
            previous_text.type = TextType.LIST

            # Headings should match for list items
            if current_text.headings != previous_text.headings:
                logger.warning(
                    "Warning: Headings don't match for list items: %s %s",
                    previous_text.text,
                    current_text.text,
                )
        else:
            # If it's not merged, just add it as a new element
            grouped_texts.append(current_text)

    return grouped_texts

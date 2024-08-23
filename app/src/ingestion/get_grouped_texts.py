import logging

from src.ingestion.pdf_elements import EnrichedText, TextType

logger = logging.getLogger(__name__)


def get_grouped_texts(markdown_texts: list[EnrichedText]) -> list[EnrichedText]:
    """
    Given EnrichedTexts, concatenate list tems together
    with each other and with the preceeding NarrativeText.
    """

    if not markdown_texts:
        return []

    grouped_texts = [markdown_texts[0]]

    for current_text in markdown_texts[1:]:
        previous_text = grouped_texts[-1]

        if current_text.type == TextType.LIST_ITEM:
            # Concatenate the current text to the previous one
            previous_text.text += "\n" + current_text.text
            previous_text.type = TextType.LIST

            # Headings should match for list items
            if current_text.headings != previous_text.headings:
                logger.warning("Warning: Headings don't match for list items.")

        else:
            # If it's not a list item, just add it as a new element
            grouped_texts.append(current_text)

    return grouped_texts

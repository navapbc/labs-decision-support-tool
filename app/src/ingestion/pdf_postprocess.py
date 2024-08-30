import logging

from src.ingestion.pdf_elements import EnrichedText, TextType
from src.ingestion.pdf_stylings import Styling
from src.util.string_utils import basic_ascii

logger = logging.getLogger(__name__)


def associate_stylings(
    enriched_texts: list[EnrichedText], stylings: list[Styling]
) -> list[EnrichedText]:
    "Given EnrichedTexts and Stylings, associate stylings to the corresponding text item"
    for e_text in enriched_texts:
        matched_stylings = [
            styling for styling in stylings if _styling_matches_text(styling, e_text)
        ]
        if matched_stylings:
            e_text.stylings = matched_stylings
    return enriched_texts


# The maximum difference in length between the Styling.wider_text and the text in the enriched text
# There could be several paragraphs on the same page and under the same heading that have a bolded word,
# e.g., "CDC" (single-word paragraph) and "CDC is the center for disease control".
# A styling.text="CDC" would match both paragraphs without this check.
_STYLING_MATCH_MAX_LENGTH_DIFF = 10


def _styling_matches_text(styling: Styling, e_text: EnrichedText) -> bool:
    # Quick checks
    if styling.pageno != e_text.page_number or styling.headings != e_text.headings:
        return False

    # Slower checks
    stripped_wider_text = basic_ascii(styling.wider_text).strip()
    stripped_e_text = basic_ascii(e_text.text).strip()
    return (
        stripped_wider_text in stripped_e_text
        and abs(len(stripped_wider_text) - len(stripped_e_text)) < _STYLING_MATCH_MAX_LENGTH_DIFF
    )


def _apply_stylings(e_text: EnrichedText) -> EnrichedText:
    "Given EnrichedTexts with stylings field, apply stylings to the text in markdown format"
    if not e_text.stylings:
        return e_text

    applied = []
    for styling in e_text.stylings:
        if styling.bold and (markdown_text := _apply_bold_styling(e_text.text, styling)):
            applied.append(styling)
            e_text.text = markdown_text

    if applied == e_text.stylings:
        e_text.stylings = None
    else:
        e_text.stylings = [s for s in e_text.stylings if s not in applied]
        logger.warning("Stylings were not applied: %s", e_text.stylings, extra={"e_text": e_text})
    return e_text


def _apply_bold_styling(text: str, styling: Styling) -> str | None:
    # Replace only the first occurrence of the styling text
    markdown_text = text.replace(styling.text, f"**{styling.text}**", 1)
    if markdown_text == text:
        return None

    # Warn if the styling text occurs multiple times
    replaced_all = text.replace(styling.text, f"**{styling.text}**")
    if replaced_all != text:
        logger.warning(
            "Styling text %s occurs multiple times; only applied to the first occurrence: '%s'",
            styling.text,
            text,
        )
    return markdown_text


def _add_link_markdown(e_text: EnrichedText) -> EnrichedText:
    "Given EnrichedTexts with links field, apply links to the text in markdown format"
    if not e_text.links:
        return e_text

    applied = []
    for link in e_text.links:
        try:
            index = e_text.text.index(link.text, link.start_index)
            e_text.text = (
                e_text.text[:index]
                + f"[{link.text}]({link.url})"
                + e_text.text[index + len(link.text) :]
            )
            applied.append(link)
        except ValueError:
            logger.warning("Link text '%s' not found in: %s", link.text, e_text.text)

    if applied == e_text.links:
        e_text.links = None
    else:
        e_text.links = [s for s in e_text.links if s not in applied]
    return e_text


def add_markdown(enriched_texts: list[EnrichedText]) -> list[EnrichedText]:
    markdown_texts = []
    for enriched_text in enriched_texts:
        # Link markdown should be applied to the text before applying stylings and
        # prepending "    - " to ListItem elements so that positional data like
        # link.start_index can be used without having to account for text transformations.
        markdown_text = _add_link_markdown(enriched_text)

        # Apply stylings before adding list item markdown since stylings rely on matching
        # style.wider_text to the original text.
        # If _add_link_markdown() modifies the styled text, the styling will not be applied
        # if styling.text crosses the link boundaries -- a warning is logged.
        # E.g., if styling.text="CDC means" and link.text="CDC", then the styling will not be applied
        # b/c markdown_text will look like "[CDC](url) means" and styling.text no longer matches.
        markdown_text = _apply_stylings(markdown_text)

        if markdown_text.type == TextType.LIST_ITEM:
            markdown_text.text = "    - " + markdown_text.text
        markdown_texts.append(markdown_text)
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

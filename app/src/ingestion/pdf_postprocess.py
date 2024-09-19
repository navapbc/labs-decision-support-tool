import logging

from src.ingestion.pdf_elements import EnrichedText, TextType
from src.ingestion.pdf_stylings import Styling
from src.util.string_utils import basic_ascii

logger = logging.getLogger(__name__)


def associate_stylings(
    enriched_texts: list[EnrichedText], stylings: list[Styling]
) -> list[EnrichedText]:
    "Given EnrichedTexts and Stylings, associate stylings to the corresponding text item"
    all_matched_stylings = []
    for e_text in enriched_texts:
        matched_stylings = [
            styling for styling in stylings if _styling_matches_text(styling, e_text)
        ]
        if matched_stylings:
            e_text.stylings = matched_stylings
            all_matched_stylings.extend(matched_stylings)

    unmatched_stylings = [s for s in stylings if s not in all_matched_stylings]
    for styling in unmatched_stylings:
        logger.warning("Styling not associated: %s", styling)
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
    # Ignore spaces when matching
    stripped_wider_text = basic_ascii(styling.wider_text).replace(" ", "")
    stripped_e_text = basic_ascii(e_text.text).replace(" ", "")
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
        logger.warning(
            "Associated stylings were not applied: %s", e_text.stylings, extra={"e_text": e_text}
        )
    return e_text


def _apply_bold_styling(text: str, styling: Styling) -> str | None:
    # Replace only the first occurrence of the styling text
    # Unstructured will strip() texts, so we need to strip the styling text as well
    styled_text = styling.text.strip()
    markdown_text = text.replace(styled_text, f"**{styled_text}**", 1)
    if markdown_text == text:
        return None

    # Warn if the styling text occurs multiple times
    replaced_all = text.replace(styled_text, f"**{styled_text}**")

    if replaced_all != markdown_text:
        logger.warning(
            "Styling text '%s' occurs multiple times; only applied to the first occurrence: '%s'",
            styled_text,
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


def _add_list_markdown(
    prev_e_text: EnrichedText | None, current_e_text: EnrichedText
) -> EnrichedText:
    if (
        prev_e_text
        and prev_e_text.type == TextType.LIST_ITEM
        and current_e_text.type == TextType.LIST_ITEM
    ):
        # if sublist, indent 2 spaces
        if "\u2022" in current_e_text.text:
            current_e_text.text = "  - " + current_e_text.text
            current_e_text.text = current_e_text.text.replace("\u2022", "\n  - ")
            list_items = current_e_text.text.split("\n")
            nonempty_items = [item for item in list_items if item.strip() and item.strip() != "-"]
            current_e_text.text = "\n".join(nonempty_items)
        else:
            current_e_text.text = "- " + current_e_text.text
    elif current_e_text.type == TextType.LIST_ITEM:
        current_e_text.text = "- " + current_e_text.text
    return current_e_text


def add_markdown(enriched_texts: list[EnrichedText]) -> list[EnrichedText]:
    markdown_texts = []
    prev_markdown_val = None
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

        markdown_text = _add_list_markdown(prev_markdown_val, markdown_text)
        prev_markdown_val = markdown_text

        markdown_texts.append(markdown_text)
    return enriched_texts


def _should_merge_list_text(text: EnrichedText, next_text: EnrichedText) -> bool:
    if text.headings != next_text.headings:
        return False

    return next_text.type == TextType.LIST_ITEM


def _group_list_texts(markdown_texts: list[EnrichedText]) -> list[EnrichedText]:
    """
    Given EnrichedTexts, concatenate list items together
    with each other and with the preceeding NarrativeText.
    """

    if not markdown_texts:
        return []

    grouped_texts = [markdown_texts[0]]

    for current_text in markdown_texts[1:]:
        previous_text = grouped_texts[-1]

        # Unstructured text sometimes splits a bullet from its text;
        # merge them back together
        # account for instances where text is separated by "-"
        if (
            previous_text.text.endswith("\n- ")
            and previous_text.type in [TextType.LIST_ITEM, TextType.LIST]
            and current_text.type == TextType.NARRATIVE_TEXT
        ):
            previous_text.text += current_text.text
            continue

        if _should_merge_list_text(previous_text, current_text):
            # Append the current text to the previous one
            previous_text.text += "\n" + current_text.text
            previous_text.type = TextType.LIST
        else:
            # If it's not merged, just add it as a new element
            grouped_texts.append(current_text)

    return grouped_texts


def _should_merge_text_split_across_pages(text: EnrichedText, next_text: EnrichedText) -> bool:
    "Check for texts that are split across consecutive pages"
    if text.headings != next_text.headings:
        return False

    assert text.page_number is not None
    assert next_text.page_number is not None
    # Check if next_text is on the next page
    if text.page_number != (next_text.page_number - 1):
        return False

    return next_text.text.strip()[0].islower()


NestedHeadingTitles = tuple[str, ...]


def _group_headings_text(markdown_texts: list[EnrichedText]) -> list[EnrichedText]:
    grouped_texts_by_headings: dict[NestedHeadingTitles, EnrichedText] = {}
    for markdown_text in markdown_texts:
        text_nested_headings: NestedHeadingTitles = tuple([h.title for h in markdown_text.headings])
        if text_nested_headings in grouped_texts_by_headings:
            grouped_texts_by_headings[text_nested_headings].text += f"\n\n{markdown_text.text}"

            # Grouping any text with a NarrativeText type makes the whole group a NarrativeText type
            if markdown_text.type == TextType.NARRATIVE_TEXT:
                grouped_texts_by_headings[text_nested_headings].type = markdown_text.type
        else:
            grouped_texts_by_headings[text_nested_headings] = EnrichedText(
                text=markdown_text.text,
                type=markdown_text.type,
                headings=markdown_text.headings,
                page_number=markdown_text.page_number,
                stylings=markdown_text.stylings,
                links=markdown_text.links,
            )

    # As of Python 3.7, dictionaries maintain insertion order
    return list(grouped_texts_by_headings.values())


def group_texts(markdown_texts: list[EnrichedText]) -> list[EnrichedText]:
    lists_merged = _group_list_texts(markdown_texts)

    if not lists_merged:
        return []

    grouped_texts = [lists_merged[0]]
    for e_text in lists_merged[1:]:
        prev_text = grouped_texts[-1]

        if _should_merge_text_split_across_pages(prev_text, e_text):
            prev_text.text += " " + e_text.text
            continue

        if prev_text.type == TextType.TITLE:
            prev_text.text += "\n\n" + e_text.text
            prev_text.type = e_text.type
            continue

        grouped_texts.append(e_text)

    grouped_texts = _group_headings_text(grouped_texts)
    return grouped_texts

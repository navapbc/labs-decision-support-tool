import logging

import pytest

from src.ingestion.pdf_elements import EnrichedText, Heading, Link, TextType
from src.ingestion.pdf_postprocess import (
    _add_link_markdown,
    _add_list_markdown,
    _apply_stylings,
    _group_headings_text,
    add_markdown,
    associate_stylings,
    group_texts,
)
from tests.src.ingestion.test_pdf_stylings import Styling, all_expected_stylings


@pytest.fixture
def enriched_texts() -> list[EnrichedText]:
    return [
        EnrichedText(
            text="Following is a list:",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1)],
        ),
        EnrichedText(
            text="First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
            links=[Link(start_index=6, text="item", url="http://www.michigan.gov")],
        ),
        EnrichedText(
            text="Second item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
            page_number=2,
            stylings=[
                Styling(
                    text="Second item",
                    pageno=2,
                    headings=[Heading(title="Section 3", level=1)],
                    wider_text="Second item.",
                    bold=True,
                )
            ],
        ),
    ]


def test_add_markdown(enriched_texts):
    result = add_markdown(enriched_texts)

    assert result == [
        EnrichedText(
            text="Following is a list:",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1)],
        ),
        EnrichedText(
            text="- First [item](http://www.michigan.gov).",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
            links=None,
        ),
        EnrichedText(
            text="- **Second item**.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
            page_number=2,
            stylings=None,
        ),
    ]


def test_empty_list():
    assert group_texts([]) == []


def test_single_narrative_text():
    texts = [
        EnrichedText(
            text="A single narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[
                Heading(title="Overview", level=1, pageno=1),
            ],
            page_number=1,
        )
    ]
    result = group_texts(texts)
    # No change
    assert result == texts


def test__group_headings_text():
    texts = [
        EnrichedText(
            text="Following is a list:",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1)],
            page_number=1,
            links=None,
        ),
        EnrichedText(
            text="- First [item](http://www.michigan.gov).\n- **Second item**.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1), Heading(title="Section 4", level=2)],
            page_number=1,
            links=None,
        ),
        EnrichedText(
            text="- **First item in new section**.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1), Heading(title="Section 5", level=2)],
            page_number=2,
            stylings=None,
        ),
        EnrichedText(
            text="- Other list item in section 3.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
            page_number=1,
            links=None,
        ),
    ]

    assert _group_headings_text(texts) == [
        EnrichedText(
            text="Following is a list:\n\n- Other list item in section 3.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1, pageno=None)],
            page_number=1,
            id=None,
            stylings=None,
            links=None,
        ),
        EnrichedText(
            text="- First [item](http://www.michigan.gov).\n- **Second item**.",
            type=TextType.LIST_ITEM,
            headings=[
                Heading(title="Section 3", level=1, pageno=None),
                Heading(title="Section 4", level=2, pageno=None),
            ],
            page_number=1,
            id=None,
            stylings=None,
            links=None,
        ),
        EnrichedText(
            text="- **First item in new section**.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1), Heading(title="Section 5", level=2)],
            page_number=2,
            stylings=None,
        ),
    ]


def test_concatenate_list_items():
    texts = [
        EnrichedText(
            text="Introduction.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="Second item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="Another narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="Narrative starting a new list: ",  # ending space is intentional
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="First item in new list.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="Second item in new list.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="New list item in new section",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(
            text="with continuing sentence on next page",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 1", level=1, pageno=1)],
            page_number=2,
        ),
    ]

    result = group_texts(texts)

    assert result == [
        EnrichedText(
            text="Introduction.\nFirst item.\nSecond item.\n\nAnother narrative text.\n\nNarrative starting a new list: \nFirst item in new list.\nSecond item in new list.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
            id=None,
            stylings=None,
            links=None,
        ),
        EnrichedText(
            text="New list item in new section with continuing sentence on next page",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1, pageno=1)],
            page_number=1,
            id=None,
            stylings=None,
            links=None,
        ),
    ]


def texts_for_stylings() -> list[EnrichedText]:
    return [
        EnrichedText(  # Should not be associated with a Styling
            text="Introduction.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, pageno=1)],
            page_number=1,
        ),
        EnrichedText(  # Substring should be bolded
            text="First occurrence - six month disqualification. The "
            "closure reason will be CDC not eligible due to 6 month "
            "penalty period.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Disqualifications", level=1, pageno=2)],
            page_number=3,
        ),
        EnrichedText(  # Substring with ending space should be bolded
            text="Second occurrence - twelve month disqualification. The "
            "closure reason will be CDC not eligible due to 12 month "
            "penalty period. ",  # ending space is intentional
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Disqualifications", level=1, pageno=2)],
            page_number=3,
        ),
        EnrichedText(  # Text string matches but different page
            text="Third occurrence - lifetime disqualification. The "
            "closure reason will be CDC not eligible due to lifetime "
            "penalty.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Disqualifications", level=1, pageno=2)],
            page_number=4,
        ),
        EnrichedText(
            text="Paragraph is too long to match CDC styling.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="legal base", level=1, pageno=4)],
            page_number=4,
        ),
        EnrichedText(  # Multiple substrings match
            text="CDC - CDC",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="legal base", level=1, pageno=4)],
            page_number=4,
        ),
    ]


def text_with_stylings():
    expected_text_with_stylings = texts_for_stylings()
    expected_text_with_stylings[1].stylings = [all_expected_stylings[0]]
    expected_text_with_stylings[2].stylings = [all_expected_stylings[1]]
    expected_text_with_stylings[5].stylings = [all_expected_stylings[4]]
    return expected_text_with_stylings


def test_associated_stylings():
    texts = texts_for_stylings()

    assert len(all_expected_stylings) == 5
    assert associate_stylings(texts.copy(), all_expected_stylings) == text_with_stylings()


def test__apply_stylings():
    texts = texts_for_stylings()
    applied = [_apply_stylings(enriched_text) for enriched_text in text_with_stylings()]

    assert applied == [
        texts[0],
        EnrichedText(  # Substring should be bolded
            text="First occurrence - six month disqualification. The "
            "closure reason will be **CDC not eligible due to 6 month "
            "penalty period**.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Disqualifications", level=1, pageno=2)],
            page_number=3,
        ),
        EnrichedText(  # Substring with ending space should be bolded
            text="Second occurrence - twelve month disqualification. The "
            "closure reason will be **CDC not eligible due to 12 month "
            "penalty period.** ",  # ending space is intentional
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Disqualifications", level=1, pageno=2)],
            page_number=3,
        ),
        # Text string matches but different page
        texts[3],
        texts[4],
        EnrichedText(  # Multiple substrings match
            text="**CDC** - CDC",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="legal base", level=1, pageno=4)],
            page_number=4,
        ),
    ]


def text_with_links():
    return [
        EnrichedText(
            text="Each state must submit a state plan for FIP. State plans are located at http://www.michigan.gov.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Family Independence Program (FIP)", level=2, pageno=1)],
            links=[
                Link(start_index=72, text="http://www.michigan.gov", url="http://www.michigan.gov"),
                Link(
                    start_index=0,
                    text="A substring that is not in the text",
                    url="http://www.michigan.gov",
                ),
            ],
        ),
        EnrichedText(
            text="The MDHHS policy manuals are available to the public at the Michigan "
            "Department of Health and Human Services internet site under MDHHS "
            "Policy Manuals; see BAM 310, Confidentiality, regarding the release "
            "of specific information pertaining to clients.",
            type=TextType.NARRATIVE_TEXT,
            headings=[
                Heading(title="Revisions", level=1, pageno=7),
                Heading(title="Public Access to Manuals", level=2, pageno=7),
            ],
            links=[
                Link(
                    start_index=4,
                    text="MDHHS policy manuals",
                    url="http://www.michigan.gov/mdhhs",
                ),
                Link(
                    start_index=129,
                    text="MDHHS Policy Manuals",
                    url="http://www.michigan.gov/mdhhs",
                ),
            ],
        ),
    ]


def test__add_link_markdown(caplog):
    with caplog.at_level(logging.WARNING):
        markdown_texts = [_add_link_markdown(enriched_text) for enriched_text in text_with_links()]

    assert "Link text 'A substring that is not in the text' not found in:" in caplog.messages[0]
    assert markdown_texts == [
        EnrichedText(
            text="Each state must submit a state plan for FIP. State plans are located at [http://www.michigan.gov](http://www.michigan.gov).",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Family Independence Program (FIP)", level=2, pageno=1)],
            links=[
                Link(
                    start_index=0,
                    text="A substring that is not in the text",
                    url="http://www.michigan.gov",
                ),
            ],
        ),
        EnrichedText(
            text="The [MDHHS policy manuals](http://www.michigan.gov/mdhhs) are available to the public at the Michigan "
            "Department of Health and Human Services internet site under [MDHHS "
            "Policy Manuals](http://www.michigan.gov/mdhhs); see BAM 310, Confidentiality, regarding the release "
            "of specific information pertaining to clients.",
            type=TextType.NARRATIVE_TEXT,
            headings=[
                Heading(title="Revisions", level=1, pageno=7),
                Heading(title="Public Access to Manuals", level=2, pageno=7),
            ],
        ),
    ]


def test_add_list_markdown(enriched_texts):
    prev_enriched_text_val = None
    first_list_level = _add_list_markdown(prev_enriched_text_val, enriched_texts[1])

    second_list_level = _add_list_markdown(
        enriched_texts[2],
        EnrichedText(
            text="• Sub nested item.  • second test message • • ",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1)],
            page_number=2,
            stylings=None,
        ),
    )

    assert first_list_level.text == "- First item."
    assert second_list_level.text == "  -  Sub nested item.  \n  -  second test message "

    list_with_multiple_bullets = _add_list_markdown(
        enriched_texts[2],
        EnrichedText(
            text="Parent/provider certifications. • Day/date. • Children's names. In/out times.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1, pageno=1)],
            page_number=2,
            stylings=None,
        ),
    )
    assert list_with_multiple_bullets == EnrichedText(
        text="  - Parent/provider certifications. \n  -  Day/date. \n  -  Children's names. In/out times.",
        type=TextType.LIST_ITEM,
        headings=[Heading(title="Section 1", level=1, pageno=1)],
        page_number=2,
        id=None,
        stylings=None,
        links=None,
    )

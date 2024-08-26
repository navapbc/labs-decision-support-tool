from src.ingestion.pdf_elements import EnrichedText, Heading, TextType
from src.ingestion.pdf_postprocess import add_markdown, group_texts


def test_add_markdown():
    enriched_texts = [
        EnrichedText(
            text="Following is a list:",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1)],
        ),
        EnrichedText(
            text="First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
        ),
    ]

    result = add_markdown(enriched_texts)

    assert result == [
        EnrichedText(
            text="Following is a list:",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Section 3", level=1)],
        ),
        EnrichedText(
            text="    - First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 3", level=1)],
        ),
    ]


def test_empty_list():
    assert group_texts([]) == []


def test_single_narrative_text():
    texts = [
        EnrichedText(
            text="A single narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        )
    ]
    result = group_texts(texts)
    # No change
    assert result == texts


def test_concatenate_list_items():
    texts = [
        EnrichedText(
            text="Introduction.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Second item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Another narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Narrative starting a new list: ",  # ending space is intentional
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="First item in new list.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Second item in new list.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="New list item in new section.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1)],
        ),
    ]

    result = group_texts(texts)

    assert result == [
        EnrichedText(
            text="Introduction.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="First item.\nSecond item.",
            type=TextType.LIST,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Another narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="Narrative starting a new list: \nFirst item in new list.\nSecond item in new list.",
            type=TextType.LIST,
            headings=[Heading(title="Overview", level=1)],
        ),
        EnrichedText(
            text="New list item in new section.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Section 1", level=1)],
        ),
    ]

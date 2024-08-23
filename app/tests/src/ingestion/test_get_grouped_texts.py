from src.ingestion.elements import EnrichedText, Heading, Page, TextType
from src.ingestion.get_grouped_texts import get_grouped_texts


def test_empty_list():
    assert get_grouped_texts([]) == []


def test_single_narrative_text():
    page = Page(pdf_page_number=1, document_page_number="1")
    texts = [
        EnrichedText(
            text="A single narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        )
    ]
    result = get_grouped_texts(texts)
    # No change
    assert result == texts


def test_concatenate_list_items():
    page = Page(pdf_page_number=1, document_page_number="1")
    texts = [
        EnrichedText(
            text="Introduction.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="First item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="Second item.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="Another narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="Narrative starting a new list.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="First item in new list.",
            type=TextType.LIST_ITEM,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
    ]

    result = get_grouped_texts(texts)

    assert len(result) == 3
    assert result == [
        EnrichedText(
            text="Introduction.\nFirst item.\nSecond item.",
            type=TextType.LIST,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="Another narrative text.",
            type=TextType.NARRATIVE_TEXT,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
        EnrichedText(
            text="Narrative starting a new list.\nFirst item in new list.",
            type=TextType.LIST,
            headings=[Heading(title="Overview", level=1, page=page)],
            page=page,
        ),
    ]

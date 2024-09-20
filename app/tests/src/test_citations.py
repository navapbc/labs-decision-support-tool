import pytest

from src.citations import add_citations, get_citation_numbers, get_context, get_context_for_prompt
from src.db.models.document import ChunkWithSubsection
from tests.src.db.models.factories import ChunkFactory


@pytest.fixture
def chunks():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    return chunks


@pytest.fixture
def context(chunks):
    return [
        ChunkWithSubsection(chunks[0], "This is the first chunk."),
        ChunkWithSubsection(chunks[0], "With two subsections"),
        ChunkWithSubsection(chunks[1], chunks[1].content),
    ]


def test_get_context_for_prompt(chunks):
    assert get_context_for_prompt([]) == ""

    assert get_context_for_prompt(chunks) == (
        f"""Citation: citation-0
Document name: {chunks[0].document.name}
Headings: {" > ".join(chunks[0].headings)}
Content: This is the first chunk.

Citation: citation-1
Document name: {chunks[0].document.name}
Headings: {" > ".join(chunks[0].headings)}
Content: With two subsections

Citation: citation-2
Document name: {chunks[1].document.name}
Headings: {" > ".join(chunks[1].headings)}
Content: {chunks[1].content}"""
    )


def test_add_citations(chunks):
    assert add_citations("This is a citation (citation-0)", []) == "This is a citation (citation-0)"

    assert (
        add_citations("This is a citation (citation-0) and another (citation-1).", chunks)
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )


def test_get_context(chunks):
    assert get_context(chunks) == [
        ChunkWithSubsection(chunks[0], "This is the first chunk."),
        ChunkWithSubsection(chunks[0], "With two subsections"),
        ChunkWithSubsection(chunks[1], chunks[1].content),
    ]


def test_get_citation_numbers(context):
    assert get_citation_numbers(context, "") == []
    assert get_citation_numbers([], "A non-existent citation is (citation-0)") == []
    assert get_citation_numbers(
        context,
        "Now a real citation is (citation-1), which we can cite twice (citation-1), followed by (citation-0)",
    ) == [context[1], context[0]]

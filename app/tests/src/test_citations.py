import pytest

from src.citations import (
    create_prompt_context,
    dereference_citations,
    reify_citations,
    split_into_subsections,
    combine_citations,
)
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
    assert create_prompt_context([]) == ""

    assert create_prompt_context(chunks) == (
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


def test_reify_citations(chunks):
    assert (
        reify_citations("This is a citation (citation-0)", []) == "This is a citation (citation-0)"
    )

    assert (
        reify_citations("This is a citation (citation-0) and another (citation-1).", chunks)
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )


def test_get_context(chunks):
    assert split_into_subsections(chunks) == [
        ChunkWithSubsection(chunks[0], "This is the first chunk."),
        ChunkWithSubsection(chunks[0], "With two subsections"),
        ChunkWithSubsection(chunks[1], chunks[1].content),
    ]


def test_combine_citations(chunks):
    chunk_with_subsections = {
        ChunkWithSubsection(chunks[0], "This is the first chunk."): 1,
        ChunkWithSubsection(chunks[0], "With two subsections"): 2,
        ChunkWithSubsection(chunks[1], chunks[1].content): 3,
    }

    assert combine_citations(chunk_with_subsections) == {
        chunks[0]: [
            {1: "This is the first chunk."},
            {2: "With two subsections"},
        ],
        chunks[1]: [{3: chunks[1].content}],
    }


def test_dereference_citationss(context):
    assert dereference_citations(context, "") == {}
    assert dereference_citations([], "A non-existent citation is (citation-0)") == {}
    assert dereference_citations(
        context,
        "Now a real citation is (citation-1), which we can cite twice (citation-1), followed by (citation-0)",
    ) == {context[1]: 1, context[0]: 2}

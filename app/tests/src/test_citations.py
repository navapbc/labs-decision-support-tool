import pytest
import dataclasses

from src.citations import (
    create_prompt_context,
    dereference_citations,
    reify_citations,
    split_into_subsections,
    CitationFactory
)
from tests.src.db.models.factories import ChunkFactory


@pytest.fixture
def chunks():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    return chunks


@pytest.fixture
def context(chunks):
    factory = CitationFactory()
    return [
        factory.create_citation(chunks[0], "This is the first chunk."),
        factory.create_citation(chunks[0], "With two subsections"),
        factory.create_citation(chunks[1], chunks[1].content),
    ]


def test_get_context_for_prompt(chunks):
    assert create_prompt_context([]) == ""

    assert create_prompt_context(chunks) == (
        f"""Citation: citation-1
Document name: {chunks[0].document.name}
Headings: {" > ".join(chunks[0].headings)}
Content: This is the first chunk.

Citation: citation-2
Document name: {chunks[0].document.name}
Headings: {" > ".join(chunks[0].headings)}
Content: With two subsections

Citation: citation-3
Document name: {chunks[1].document.name}
Headings: {" > ".join(chunks[1].headings)}
Content: {chunks[1].content}"""
    )


def test_reify_citations(chunks):
    assert (
        reify_citations("This is a citation (citation-0)", []) == "This is a citation (citation-0)"
    )

    subsections = split_into_subsections(chunks, factory = CitationFactory())
    print("INPUT:", f"This is a citation ({subsections[0].id}) and another ({subsections[1].id}).")
    assert (
        reify_citations(f"This is a citation ({subsections[0].id}) and another ({subsections[1].id}).", subsections)
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )


def test_get_context(chunks):
    subsections = split_into_subsections(chunks)
    assert subsections[0].chunk == chunks[0]
    assert subsections[0].subsection == "This is the first chunk."
    assert subsections[1].chunk == chunks[0]
    assert subsections[1].subsection == "With two subsections"
    assert subsections[2].chunk == chunks[1]
    assert subsections[2].subsection == chunks[1].content

    # Provide a factory to reset the citation id counter
    subsections = split_into_subsections(chunks, factory = CitationFactory())
    assert subsections[0].id == "citation-1"
    assert subsections[1].id == "citation-2"
    assert subsections[2].id == "citation-3"


def test_dereference_citations(context):
    assert dereference_citations(context, "") == []
    assert dereference_citations([], "A non-existent citation is (citation-0)") == []
    assert dereference_citations(
        context,
        f"Now a real citation is ({context[1].id}), which we can cite twice ({context[1].id}), followed by ({context[0].id})",
    ) == [dataclasses.replace(context[1], id="1"), dataclasses.replace(context[0], id="2")]

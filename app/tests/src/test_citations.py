import pytest

from src.citations import (
    CitationFactory,
    create_prompt_context,
    remap_citation_ids,
    split_into_subsections,
)
from tests.src.db.models.factories import ChunkFactory


@pytest.fixture
def chunks():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    return chunks


@pytest.fixture
def subsections(chunks):
    # Provide a factory to reset the citation id counter
    return split_into_subsections(chunks, factory=CitationFactory())


@pytest.fixture
def context(chunks):
    factory = CitationFactory()
    return [
        factory.create_citation(chunks[0], "This is the first chunk."),
        factory.create_citation(chunks[0], "With two subsections"),
        factory.create_citation(chunks[1], chunks[1].content),
    ]


def test_get_context_for_prompt(chunks, subsections):
    assert create_prompt_context([]) == ""

    assert create_prompt_context(subsections) == (
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


def test_get_context(chunks, subsections):
    assert subsections[0].id == "citation-1"
    assert subsections[0].chunk == chunks[0]
    assert subsections[0].subsection == "This is the first chunk."
    assert subsections[1].id == "citation-2"
    assert subsections[1].chunk == chunks[0]
    assert subsections[1].subsection == "With two subsections"
    assert subsections[2].id == "citation-3"
    assert subsections[2].chunk == chunks[1]
    assert subsections[2].subsection == chunks[1].content


def test_remap_citation_ids(subsections):
    assert remap_citation_ids(subsections, "") == {}
    assert remap_citation_ids([], "A non-existent citation is (citation-0)") == {}
    assert remap_citation_ids(
        subsections,
        f"Now a real citation is ({subsections[1].id}), which we can cite twice ({subsections[1].id}), followed by ({subsections[0].id})",
    ) == {
        subsections[1].id: subsections[1]._replace(id="1"),
        subsections[0].id: subsections[0]._replace(id="2"),
    }

import dataclasses

import pytest

from src.citations import (
    CitationFactory,
    combine_citations_by_document,
    create_prompt_context,
    remap_citation_ids,
    split_into_subsections,
)
from src.db.models.document import ChunkWithSubsection
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


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
        subsections[1].id: dataclasses.replace(subsections[1], id="1"),
        subsections[0].id: dataclasses.replace(subsections[0], id="2"),
    }

def test_get_context(chunks):
    assert split_into_subsections(chunks) == [
        ChunkWithSubsection(chunks[0], "This is the first chunk."),
        ChunkWithSubsection(chunks[0], "With two subsections"),
        ChunkWithSubsection(chunks[1], chunks[1].content),
    ]


def test_combine_citations_by_document():
    docs = DocumentFactory.build_batch(2)
    for doc in docs:
        doc.name += "BEM 123"
    chunk_list = ChunkFactory.build_batch(4)

    chunk_list[0].document = docs[0]
    chunk_list[1].document = docs[0]
    chunk_list[2].document = docs[1]
    chunk_list[3].document = docs[1]

    chunks_items = {
        ChunkWithSubsection(chunk_list[0], "Subsection 1"): 1,
        ChunkWithSubsection(chunk_list[0], "Subsection 2"): 2,
        ChunkWithSubsection(chunk_list[1], "Subsection 3"): 3,
        ChunkWithSubsection(chunk_list[2], "Subsection 5"): 5,
        ChunkWithSubsection(chunk_list[3], "Subsection 6"): 6,
    }
    # Check for items with the same chunk and different subsections
    assert combine_citations_by_document(chunks_items) == {
        docs[0]: [
            {chunk_list[0]: [{1: "Subsection 1"}, {2: "Subsection 2"}]},
            {chunk_list[1]: [{3: "Subsection 3"}]},
        ],
        docs[1]: [{chunk_list[2]: [{5: "Subsection 5"}]}, {chunk_list[3]: [{6: "Subsection 6"}]}],
    }

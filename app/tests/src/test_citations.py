import pytest

from src.citations import (
    CitationFactory,
    basic_chunk_splitter,
    create_prompt_context,
    default_chunk_splitter,
    remap_citation_ids,
    replace_citation_ids,
    split_into_subsections,
    tree_based_chunk_splitter,
)
from src.db.models.document import Subsection
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
    assert subsections[0].text == "This is the first chunk."
    assert subsections[1].id == "citation-2"
    assert subsections[1].chunk == chunks[0]
    assert subsections[1].text == "With two subsections"
    assert subsections[2].id == "citation-3"
    assert subsections[2].chunk == chunks[1]
    assert subsections[2].text == chunks[1].content


def test_remap_citation_ids(subsections):
    assert remap_citation_ids(subsections, "") == {}
    assert remap_citation_ids([], "A non-existent citation is (citation-0)") == {}

    remapped_citations = remap_citation_ids(
        subsections,
        f"Now a real citation is ({subsections[1].id}), which we can cite twice ({subsections[1].id}), followed by ({subsections[0].id})",
    )
    assert remapped_citations[subsections[1].id].id == "1"
    assert remapped_citations[subsections[0].id].id == "2"


def test_default_chunk_splitter():
    pass


CHUNK_CONTENT = (
    "## My Heading\n\n"
    "First paragraph.\n\n"
    "Paragraph two.\n\n"
    "And paragraph 3\n\n"
    "### Heading with empty next paragraph\n\n"
    "### Heading 3\n\n"
    "Paragraph under H3.\n\n"
    "## Last Heading\n\n"
    "Last paragraph.\n\n"
    "## Last Heading without next paragraph\n"
)
EXPECTED_SUBSECTIONS = [
    (["Heading 1", "My Heading"], "First paragraph."),
    (["Heading 1", "My Heading"], "Paragraph two."),
    (["Heading 1", "My Heading"], "And paragraph 3"),
    (["Heading 1", "My Heading", "Heading 3"], "Paragraph under H3."),
    (["Heading 1", "Last Heading"], "Last paragraph."),
]


def test_basic_chunk_splitter():
    chunk = ChunkFactory.build(content=CHUNK_CONTENT, headings=["Heading 1"])
    subsections = basic_chunk_splitter(chunk)
    assert [
        (subsection.text_headings, subsection.text) for subsection in subsections
    ] == EXPECTED_SUBSECTIONS


def test_tree_based_chunk_splitter():
    chunk = ChunkFactory.build(content=CHUNK_CONTENT, headings=["Heading 1"])
    subsections = tree_based_chunk_splitter(chunk)
    assert [
        (subsection.text_headings, subsection.text) for subsection in subsections
    ] == EXPECTED_SUBSECTIONS


def test_replace_citation_ids():
    assert replace_citation_ids("No citations", {}) == "No citations"
    assert replace_citation_ids("Hallucinated.(citation-1)", {}) == "Hallucinated."

    remapped_citations = {
        "citation-4": Subsection("1", ChunkFactory.build(), ""),
        "citation-3": Subsection("2", ChunkFactory.build(), ""),
    }
    assert (
        replace_citation_ids("Remapped. (citation-4)(citation-3)", remapped_citations)
        == "Remapped. (citation-1)(citation-2)"
    )

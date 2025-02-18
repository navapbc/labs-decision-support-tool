from textwrap import dedent

import pytest

from src.citations import (
    CitationFactory,
    basic_chunk_splitter,
    create_prompt_context,
    move_citations_after_punctuation,
    remap_citation_ids,
    replace_citation_ids,
    split_into_subsections,
    tree_based_chunk_splitter,
)
from src.db.models.document import Chunk, Subsection
from tests.src.db.models.factories import ChunkFactory


@pytest.fixture
def chunks():
    chunks = ChunkFactory.build_batch(3)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    chunks[2].content = (
        "Chunk with a table\n\n"
        "| Header 1 | Header 2 |\n"
        "| -------- | -------- |\n"
        "| Value 1  | Value 2  |"
    )
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
Content: {chunks[1].content}

Citation: citation-4
Document name: {chunks[2].document.name}
Headings: {" > ".join(chunks[2].headings)}
Content: Chunk with a table

Citation: citation-5
Document name: {chunks[2].document.name}
Headings: {" > ".join(chunks[2].headings)}
Content: | Header 1 | Header 2 |
| -------- | -------- |
| Value 1  | Value 2  |"""
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
    assert subsections[3].text == "Chunk with a table"
    assert subsections[4].text == (
        "| Header 1 | Header 2 |\n"  #
        "| -------- | -------- |\n"  #
        "| Value 1  | Value 2  |"
    )


def test_remap_citation_ids(subsections):
    assert remap_citation_ids(subsections, "") == {}
    assert remap_citation_ids([], "A non-existent citation is (citation-0)") == {}

    remapped_citations = remap_citation_ids(
        subsections,
        f"Now a real citation is ({subsections[1].id}), which we can cite twice ({subsections[1].id}), followed by ({subsections[0].id})",
    )
    assert remapped_citations[subsections[1].id].id == "1"
    assert remapped_citations[subsections[0].id].id == "2"


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
    chunk_content = CHUNK_CONTENT + (
        "## Some Heading\n"  #
        "Text with no empty line between heading and paragraph."
    )
    chunk = ChunkFactory.build(content=chunk_content, headings=["Heading 1"])
    subsections = tree_based_chunk_splitter(chunk)
    assert [
        (subsection.text_headings, subsection.text) for subsection in subsections
    ] == EXPECTED_SUBSECTIONS + [
        (["Heading 1", "Some Heading"], "Text with no empty line between heading and paragraph."),
    ]


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


def test_intro_sentence_for_list():
    my_chunk_text = """When someone applies for a Green Card through a family petition, the immigration officials can deny the application for different reasons. One reason is if the government thinks the person is likely to depend too much on public benefits in the future. This is called the Public Charge Rule.

The immigration officer will consider the immigrant's:

* Health
* Age
* Income/resources
* Education and skills
* Family size and potential sponsor
* Receiving the two kinds of public benefits listed below

The officer weighs all these factors. They consider positive factors, like a job or skills or support from a sponsor. They consider negative factors, like low income or health problems. If an immigrant receives a counted benefit, officials will look at how recently and for how long. They do *not* consider benefits received for family members. They can deny the application if they think the person will depend too much on public benefits in the future.
"""
    my_chunk = Chunk(content=my_chunk_text, headings=["Public Charge Rule"])
    subsections = split_into_subsections([my_chunk], factory=CitationFactory())

    assert subsections[0].text.startswith("When someone applies for a Green Card")
    assert subsections[1].text.startswith("The immigration officer will consider")
    assert "* Health" in subsections[1].text
    assert subsections[2].text.startswith("The officer weighs all these factors.")


def test_move_citations_after_punctuation():
    text = dedent(
        """
                     Some text (citation-1). Another sentence on same line with no space(citation-2)? Sentence 3 has the correct citation formatting. (citation-3)
                     - Bullet is on a new line (citation-4)!
                     Last sentence(citation-99)!

                     New paragraph (citation-100).
                  """
    )
    expected_text = dedent(
        """
                            Some text. (citation-1)
                            Another sentence on same line with no space? (citation-2)
                            Sentence 3 has the correct citation formatting. (citation-3)
                            - Bullet is on a new line! (citation-4)
                            Last sentence! (citation-99)

                            New paragraph. (citation-100)
                           """
    ).strip()
    assert move_citations_after_punctuation(text) == expected_text

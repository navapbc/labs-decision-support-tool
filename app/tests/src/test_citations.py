import copy
from textwrap import dedent

import pytest

from src.citations import (
    CitationFactory,
    basic_chunk_splitter,
    create_prompt_context,
    merge_contiguous_cited_subsections,
    move_citations_after_punctuation,
    remap_citation_ids,
    replace_citation_ids,
    simplify_citation_numbers,
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
        factory.create_citation(chunks[0], 0, "This is the first chunk."),
        factory.create_citation(chunks[0], 1, "With two subsections"),
        factory.create_citation(chunks[1], 0, chunks[1].content),
    ]


def test_create_prompt_context(chunks, subsections):
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


def test_split_into_subsections(chunks, subsections):
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

    remapped_citations = {
        "citation-4": Subsection("1", ChunkFactory.build(), 0, ""),
        "citation-3": Subsection("2", ChunkFactory.build(), 1, ""),
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
        - Bullet 1 is on a new line (citation-4) (citation-5)!
        - Bullet 2 is on next line (citation-14) (citation-15) (citation-16).
        Last sentence(citation-6)!

        New paragraph (citation-100).
        """
    )
    expected_text = dedent(
        """
        Some text. (citation-1) Another sentence on same line with no space? (citation-2) Sentence 3 has the correct citation formatting. (citation-3)
        - Bullet 1 is on a new line! (citation-4) (citation-5)
        - Bullet 2 is on next line. (citation-14) (citation-15) (citation-16)
        Last sentence! (citation-6)

        New paragraph. (citation-100)
        """
    ).strip()
    assert move_citations_after_punctuation(text) == expected_text


def test_merge_contiguous_cited_subsections(subsections):
    # Ensure we have some contiguous subsections
    assert subsections[0].chunk == subsections[1].chunk
    assert subsections[0].subsection_index == 0
    assert subsections[1].subsection_index == 1

    assert subsections[3].chunk == subsections[4].chunk
    assert subsections[3].subsection_index == 0
    assert subsections[4].subsection_index == 1

    noncontig_subsection = subsections[2]

    subsection = subsections[3]
    contig_subsection = subsections[4]
    # Append a third contiguous subsection
    contig_subsection2 = copy.copy(contig_subsection)
    contig_subsection2.subsection_index = 2
    contig_subsection2.id = f"citation-{len(subsections) + 1}"
    contig_subsection2.text = "Third contiguous subsection text about topic B."
    subsections.append(contig_subsection2)

    llm_response = dedent(
        f"Something about B. ({subsection.id}) ({contig_subsection.id}) ({contig_subsection2.id}) "
        f"Some topic related to B. ({noncontig_subsection.id}) "
        f"Something about topic A. ({subsections[0].id}) ({subsections[1].id}) ({noncontig_subsection.id}) "
        f"Repeated citation to topic A. ({subsections[0].id}) ({subsections[1].id}) "
        f"Single citation from contiguous group to topic B. ({contig_subsection.id}) "
        f"Reverse order citations to topic B. ({contig_subsection.id}) ({subsection.id}) "
    )
    m_response, m_subsections = merge_contiguous_cited_subsections(llm_response, subsections)

    assert m_response == (
        "Something about B. (citation-000400050006) "
        "Some topic related to B. (citation-3) "
        "Something about topic A. (citation-00010002) (citation-3) "
        "Repeated citation to topic A. (citation-00010002) "
        "Single citation from contiguous group to topic B. (citation-5) "
        "Reverse order citations to topic B. (citation-5) (citation-4) "
    )

    # Check new citations
    subsection_dict = {ss.id: ss for ss in m_subsections}
    citation_aboutB = subsection_dict["citation-000400050006"]
    assert citation_aboutB.text == "\n\n".join(
        [subsection.text, contig_subsection.text, contig_subsection2.text]
    )

    citation_aboutA = subsection_dict["citation-00010002"]
    assert citation_aboutA.text == "\n\n".join([subsections[0].text, subsections[1].text])

    citation_3 = subsection_dict["citation-3"]
    assert citation_3 == noncontig_subsection

    remapped_citations = remap_citation_ids(m_subsections, m_response)
    remapped_response = replace_citation_ids(m_response, remapped_citations)

    print("Remapped response:", remapped_response)
    assert remapped_response == (
        "Something about B. (citation-1) "
        "Some topic related to B. (citation-2) "
        "Something about topic A. (citation-3) (citation-2) "
        "Repeated citation to topic A. (citation-3) "
        "Single citation from contiguous group to topic B. (citation-4) "
        "Reverse order citations to topic B. (citation-4) (citation-5) "
    )

    remapped_subsections = {ss.id: ss for ss in remapped_citations.values()}
    assert remapped_subsections["1"].text == citation_aboutB.text
    assert remapped_subsections["2"].text == noncontig_subsection.text
    assert remapped_subsections["3"].text == citation_aboutA.text
    assert remapped_subsections["4"].text == contig_subsection.text
    assert remapped_subsections["5"].text == subsection.text


def test_simplify_citation_numbers(subsections):
    # Test empty response
    result = simplify_citation_numbers("", subsections)
    assert result.response == ""
    assert len(result.subsections) == 0

    # Test non-existent citation
    result = simplify_citation_numbers("Non-existent citation: (citation-0)", [])
    assert result.response == "Non-existent citation:"
    assert len(result.subsections) == 0

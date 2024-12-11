import re

from sqlalchemy import delete

from src.citations import CitationFactory, split_into_subsections
from src.db.models.document import Chunk, ChunkWithScore, Document, Subsection
from src.format import (
    BemFormattingConfig,
    FormattingConfig,
    _add_ellipses_for_bem,
    _get_breadcrumb_html,
    build_accordions,
    format_bem_documents,
    reify_citations,
)
from src.retrieve import retrieve_with_scores
from tests.src.db.models.factories import ChunkFactory, DocumentFactory
from tests.src.test_retrieve import _create_chunks


def _get_chunks_with_scores():
    _create_chunks()
    return retrieve_with_scores("Very tiny words.", retrieval_k=2, retrieval_k_min_score=0.0)


def _unique_accordion_ids(html):
    return set(
        [html[m.start() + 4 : m.end() - 1] for m in re.finditer(" id=accordion-\\d*>", html)]
    )


def to_subsections(chunks_with_scores):
    return split_into_subsections([c.chunk for c in chunks_with_scores], factory=CitationFactory())


def test_format_bem_documents():
    docs = DocumentFactory.build_batch(4)
    for doc in docs:
        doc.name += "BEM 123"

    chunks_with_scores = [
        # This document is ignored because below chunks_shown_min_score
        ChunkWithScore(ChunkFactory.build(document=docs[0]), 0.90),
        # This document is excluded because chunks_shown_max_num = 2,
        # and it has the lowest score of the three documents with chunks over
        # the chunks_shown_min_score threshold
        ChunkWithScore(ChunkFactory.build(document=docs[1]), 0.92),
        # This document is included because a chunk puts
        # it over the chunks_shown_min_score threshold
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.90),
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.93),
        # This document is included, but only once
        # And it will be displayed first because it has the highest score
        ChunkWithScore(ChunkFactory.build(document=docs[3]), 0.94),
        ChunkWithScore(ChunkFactory.build(document=docs[3]), 0.95),
    ]

    html = format_bem_documents(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.91,
        chunks_with_scores=chunks_with_scores,
        subsections=to_subsections(chunks_with_scores),
        raw_response="",
    )

    assert docs[0].content not in html
    assert docs[1].content not in html
    assert docs[3].content in html
    assert "Citation 2" in html
    assert "Citation 3" not in html


def test__add_ellipses():
    one_chunk = Chunk(num_splits=0, split_index=0, content="This is the only chunk.")
    assert _add_ellipses_for_bem(one_chunk) == "This is the only chunk."

    first_chunk = Chunk(num_splits=3, split_index=0, content="This is the first chunk of 3.")
    assert _add_ellipses_for_bem(first_chunk) == "This is the first chunk of 3. ..."

    middle_chunk = Chunk(num_splits=3, split_index=2, content="This is a chunk in between.")
    assert _add_ellipses_for_bem(middle_chunk) == "... This is a chunk in between. ..."

    last_chunk = Chunk(num_splits=3, split_index=3, content="This is the last chunk.")
    assert _add_ellipses_for_bem(last_chunk) == "... This is the last chunk."

    multiple_ellipses = Chunk(
        num_splits=3, split_index=0, content="This is a chunk with multiple ellipses......"
    )
    assert (
        _add_ellipses_for_bem(multiple_ellipses)
        == "This is a chunk with multiple ellipses...... ..."
    )


def test_build_accordions_for_bem(chunks_with_scores):
    subsections = to_subsections(chunks_with_scores)

    config = BemFormattingConfig()
    assert build_accordions(subsections, "", config) == "<div></div>"
    assert (
        build_accordions([], "Non-existant citation: (citation-0)", config)
        == "<div><p>Non-existant citation: </p></div>"
    )

    assert (
        build_accordions([], "List intro sentence: \n- item 1\n- item 2", config)
        == "<div><p>List intro sentence: </p>\n<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul></div>"
    )

    chunks_with_scores[0].chunk.document.name = "BEM 100: Intro"
    chunks_with_scores[1].chunk.document.name = "BEM 101: Another"
    html = build_accordions(subsections, "Some real citations: (citation-1) (citation-2)", config)
    assert len(_unique_accordion_ids(html)) == 2


def test_reify_citations():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    subsections = split_into_subsections(chunks, factory=CitationFactory())
    config = FormattingConfig()

    assert reify_citations("This is a citation (citation-0)", [], config) == "This is a citation "

    assert (
        reify_citations(
            f"This is a citation ({subsections[0].id}) and another ({subsections[1].id}).",
            subsections,
            config,
        )
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )


def test__get_breadcrumb_html():
    headings = []
    assert _get_breadcrumb_html(headings, "Doc name") == "<div>&nbsp;</div>"

    # Omit first heading
    headings = ["Heading 1", "Heading 2", "Heading 3"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 2 → Heading 3</b></div>"

    # Omit empty headings
    headings = ["Heading 1", "", "Heading 3"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 1 → Heading 3</b></div>"

    # Omit headings that match doc name
    headings = ["Doc name", "Heading 2"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 2</b></div>"


def test__get_citation_link():
    doc = DocumentFactory.build_batch(2)
    chunk_list = ChunkFactory.build_batch(2)
    doc[0].name = "BEM 234"
    doc[1].source = "webpage 1"

    chunk_list[0].document = doc[0]
    chunk_list[0].page_number = 3

    chunk_list[1].document = doc[1]
    chunk_list[1].page_number = 3

    bem_link = BemFormattingConfig().get_citation_link(
        Subsection("1", chunk_list[0], "Subsection 1")
    )

    assert "Open document to page 3" in bem_link
    assert "Source" not in bem_link

    web_link = FormattingConfig().get_citation_link(Subsection("2", chunk_list[1], "Subsection 1"))
    assert "page 3" not in web_link
    assert "Source" in web_link


def test_build_accordions(chunks_with_scores):
    subsections = to_subsections(chunks_with_scores)

    config = FormattingConfig()
    assert build_accordions(subsections, "", config) == "<div></div>"
    assert (
        build_accordions([], "Non-existant citation: (citation-0)", config)
        == "<div><p>Non-existant citation: </p></div>"
    )

    assert (
        build_accordions([], "List intro sentence: \n- item 1\n- item 2", config)
        == "<div><p>List intro sentence: </p>\n<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul></div>"
    )

    html = build_accordions(subsections, "Some real citations: (citation-1) (citation-2)", config)
    assert len(_unique_accordion_ids(html)) == 2

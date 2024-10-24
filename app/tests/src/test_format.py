import re

from sqlalchemy import delete

from src.citations import CitationFactory, split_into_subsections
from src.db.models.document import Chunk, ChunkWithScore, Document, Subsection
from src.format import (
    _add_ellipses,
    _format_to_accordion_html,
    _get_breadcrumb_html,
    _group_by_document_and_chunks,
    format_bem_documents,
    format_bem_subsections,
    format_guru_cards,
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


def test_format_guru_cards_with_score(monkeypatch, app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))

    chunks_with_scores = _get_chunks_with_scores()
    subsections = to_subsections(chunks_with_scores)

    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.0,
        chunks_with_scores=chunks_with_scores,
        subsections=subsections,
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == len(chunks_with_scores)
    assert "Related Guru cards" in html
    assert chunks_with_scores[0].chunk.document.name in html
    assert chunks_with_scores[0].chunk.document.content in html
    assert chunks_with_scores[1].chunk.document.name in html
    assert chunks_with_scores[1].chunk.document.content in html
    assert "Similarity Score" in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.0,
        chunks_with_scores=chunks_with_scores,
        subsections=subsections,
        raw_response="",
    )
    assert len(_unique_accordion_ids(html + next_html)) == 2 * len(chunks_with_scores)


def test_format_guru_cards_given_chunks_shown_max_num(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.8,
        chunks_with_scores=chunks_with_scores,
        subsections=to_subsections(chunks_with_scores),
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == 2


def test_format_guru_cards_given_chunks_shown_max_num_and_min_score(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.91,
        chunks_with_scores=chunks_with_scores,
        subsections=to_subsections(chunks_with_scores),
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == 1


def test__format_to_accordion_html(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    chunks_with_scores = _get_chunks_with_scores()
    document = chunks_with_scores[0].chunk.document
    score = 0.92
    html = _format_to_accordion_html(document=document, score=score)
    assert document.name in html
    assert document.content in html
    assert "<p>Similarity Score: 0.92</p>" in html


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
    assert _add_ellipses(one_chunk) == "This is the only chunk."

    first_chunk = Chunk(num_splits=3, split_index=0, content="This is the first chunk of 3.")
    assert _add_ellipses(first_chunk) == "This is the first chunk of 3. ..."

    middle_chunk = Chunk(num_splits=3, split_index=2, content="This is a chunk in between.")
    assert _add_ellipses(middle_chunk) == "... This is a chunk in between. ..."

    last_chunk = Chunk(num_splits=3, split_index=3, content="This is the last chunk.")
    assert _add_ellipses(last_chunk) == "... This is the last chunk."

    multiple_ellipses = Chunk(
        num_splits=3, split_index=0, content="This is a chunk with multiple ellipses......"
    )
    assert _add_ellipses(multiple_ellipses) == "This is a chunk with multiple ellipses...... ..."


def test_format_bem_subsections(chunks_with_scores):
    subsections = to_subsections(chunks_with_scores)

    assert format_bem_subsections(0, 0, chunks_with_scores, subsections, "") == "<div></div>"
    assert (
        format_bem_subsections(0, 0, [], [], "Non-existant citation: (citation-0)")
        == "<div><p>Non-existant citation: (citation-0)</p></div>"
    )

    assert (
        format_bem_subsections(0, 0, [], [], "List intro sentence: \n- item 1\n- item 2")
        == "<div><p>List intro sentence: </p>\n<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul></div>"
    )

    chunks_with_scores[0].chunk.document.name = "BEM 100: Intro"
    chunks_with_scores[1].chunk.document.name = "BEM 101: Another"
    html = format_bem_subsections(
        0, 0, chunks_with_scores, subsections, "Some real citations: (citation-1) (citation-2)"
    )
    assert len(_unique_accordion_ids(html)) == 2


def test_reify_citations():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    subsections = split_into_subsections(chunks, factory=CitationFactory())

    assert (
        reify_citations("This is a citation (citation-0)", []) == "This is a citation (citation-0)"
    )

    assert (
        reify_citations(
            f"This is a citation ({subsections[0].id}) and another ({subsections[1].id}).",
            subsections,
        )
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )


def test__group_by_document_and_chunks():
    docs = DocumentFactory.build_batch(2)
    for doc in docs:
        doc.name += "BEM 123"
    chunk_list = ChunkFactory.build_batch(4)

    chunk_list[0].document = docs[0]
    chunk_list[1].document = docs[0]
    chunk_list[2].document = docs[1]
    chunk_list[3].document = docs[1]

    subsections = [
        Subsection("1", chunk_list[0], "Subsection 1"),
        Subsection("2", chunk_list[0], "Subsection 2"),
        Subsection("3", chunk_list[1], "Subsection 3"),
        Subsection("4", chunk_list[2], "Subsection 5"),
        Subsection("5", chunk_list[3], "Subsection 6"),
    ]
    remapped_citations = {
        "citation-22": subsections[0],
        "citation-21": subsections[1],
        "citation-20": subsections[2],
        "citation-27": subsections[3],
        "citation-25": subsections[4],
    }
    # Check for items with the same chunk and different subsections
    assert _group_by_document_and_chunks(remapped_citations) == {
        docs[0]: [
            (chunk_list[0], [subsections[0], subsections[1]]),
            (chunk_list[1], [subsections[2]]),
        ],
        docs[1]: [
            (chunk_list[2], [subsections[3]]),  #
            (chunk_list[3], [subsections[4]]),
        ],
    }


def test__get_breadcrumb_html():
    headings = []
    assert _get_breadcrumb_html(headings) == "<div>&nbsp;</div>"

    headings = ["Heading 1", "Heading 2", "Heading 3"]
    assert _get_breadcrumb_html(headings) == "<div><b>Heading 1 → Heading 2 → Heading 3</b></div>"

    headings = ["Heading 1", "", "Heading 3"]
    assert _get_breadcrumb_html(headings) == "<div><b>Heading 1 → Heading 3</b></div>"

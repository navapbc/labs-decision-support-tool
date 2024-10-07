import re

from sqlalchemy import delete

from src.db.models.document import Chunk, ChunkWithScore, Document
from src.format import (
    _add_ellipses,
    _format_to_accordion_html,
    format_bem_documents,
    format_bem_subsections,
    format_guru_cards,
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


def test_format_guru_cards_with_score(monkeypatch, app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))

    chunks_with_scores = _get_chunks_with_scores()
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.0,
        chunks_with_scores=chunks_with_scores,
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
        raw_response="",
    )
    assert len(_unique_accordion_ids(html + next_html)) == 2 * len(chunks_with_scores)


def test_format_guru_cards_given_chunks_shown_max_num(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.8,
        chunks_with_scores=chunks_with_scores,
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == 2


def test_format_guru_cards_given_chunks_shown_max_num_and_min_score(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.91,
        chunks_with_scores=chunks_with_scores,
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
    assert format_bem_subsections(0, 0, chunks_with_scores, "") == "<div></div>"
    assert (
        format_bem_subsections(0, 0, [], "Non-existant citation: (citation-0)")
        == "<div><p>Non-existant citation: (citation-0)</p></div>"
    )

    chunks_with_scores[0].chunk.document.name = "BEM 100: Intro"
    chunks_with_scores[1].chunk.document.name = "BEM 101: Another"
    html = format_bem_subsections(
        0, 0, chunks_with_scores, "Some real citations: (citation-0) (citation-1)"
    )
    assert len(_unique_accordion_ids(html)) == 2

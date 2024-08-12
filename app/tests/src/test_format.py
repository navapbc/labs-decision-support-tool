import re

from sqlalchemy import delete

from src.db.models.document import ChunkWithScore, Document
from src.format import _format_to_accordion_html, format_bem_documents, format_guru_cards
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
        docs_shown_max_num=2, docs_shown_min_score=0.0, chunks_with_scores=chunks_with_scores
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
        docs_shown_max_num=2, docs_shown_min_score=0.0, chunks_with_scores=chunks_with_scores
    )
    assert len(_unique_accordion_ids(html + next_html)) == 2 * len(chunks_with_scores)


def _chunks_with_scores():
    return [
        ChunkWithScore(ChunkFactory.build(), 0.99),
        ChunkWithScore(ChunkFactory.build(), 0.90),
        ChunkWithScore(ChunkFactory.build(), 0.85),
    ]


def test_format_guru_cards_given_docs_shown_max_num():
    html = format_guru_cards(
        docs_shown_max_num=2, docs_shown_min_score=0.8, chunks_with_scores=_chunks_with_scores()
    )
    assert len(_unique_accordion_ids(html)) == 2


def test_format_guru_cards_given_docs_shown_max_num_and_min_score():
    html = format_guru_cards(
        docs_shown_max_num=2, docs_shown_min_score=0.91, chunks_with_scores=_chunks_with_scores()
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

    chunks_with_scores = [
        # This document is ignored because below docs_shown_min_score
        ChunkWithScore(ChunkFactory.build(document=docs[0]), 0.90),
        # This document is excluded because docs_shown_max_num = 2,
        # and it has the lowest score of the three documents with chunks over
        # the docs_shown_min_score threshold
        ChunkWithScore(ChunkFactory.build(document=docs[1]), 0.92),
        # This document is included because a chunk puts
        # it over the docs_shown_min_score threshold
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.90),
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.93),
        # This document is included, but only once
        # And it will be displayed first because it has the highest score
        ChunkWithScore(ChunkFactory.build(document=docs[3]), 0.94),
        ChunkWithScore(ChunkFactory.build(document=docs[3]), 0.95),
    ]

    html = format_bem_documents(
        docs_shown_max_num=2, docs_shown_min_score=0.91, chunks_with_scores=chunks_with_scores
    )

    assert docs[0].content not in html
    assert docs[1].content not in html
    assert docs[3].content in html
    assert "Citation #2" in html
    assert "Citation #3" not in html
    assert "<p>Similarity Score: 0.95</p>" in html

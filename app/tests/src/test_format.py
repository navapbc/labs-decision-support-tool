import re

from sqlalchemy import delete

from src.db.models.document import Chunk, ChunkWithScore, Document
from src.format import format_guru_cards
from src.retrieve import retrieve_with_scores
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
        ChunkWithScore(Chunk(document=Document(name="name1", content="content1")), 0.99),
        ChunkWithScore(Chunk(document=Document(name="name2", content="content2")), 0.90),
        ChunkWithScore(Chunk(document=Document(name="name3", content="content3")), 0.85),
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

import re

from sqlalchemy import delete

from src.db.models.document import ChunkWithScore, Document
from src.format import format_bem_documents, format_guru_cards
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


def test_format_bem_documents():
    docs = (
        DocumentFactory.build(name="BEM 100: INTRODUCTION"),
        DocumentFactory.build(
            name="BEM 230A: EMPLOYMENT AND/OR SELF-SUFFICIENCY RELATED ACTIVITIES: FIP"
        ),
        DocumentFactory.build(name="BEM 400: ASSETS"),
    )

    chunks_with_scores = [
        # This document is ignored because the score is below docs_shown_min_score
        ChunkWithScore(ChunkFactory.build(document=docs[0]), 0.89),
        # Only the second chunk of this document is included
        # because docs_shown_max_num is 3
        ChunkWithScore(ChunkFactory.build(document=docs[1]), 0.92),
        ChunkWithScore(ChunkFactory.build(document=docs[1]), 0.93),
        # These are included, and this document is shown first
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.94),
        ChunkWithScore(ChunkFactory.build(document=docs[2]), 0.95),
    ]

    html = format_bem_documents(
        docs_shown_max_num=3, docs_shown_min_score=0.91, chunks_with_scores=chunks_with_scores
    )
    assert html == (
        """<h3>Source(s)</h3><ul>
<li><a href="https://dhhs.michigan.gov/olmweb/ex/BP/Public/BEM/400.pdf">BEM 400</a>: Assets<ol>
<li>Citation #1 (score: 0.95)</li>
<li>Citation #2 (score: 0.94)</li>
</ol></li>
<li><a href="https://dhhs.michigan.gov/olmweb/ex/BP/Public/BEM/230A.pdf">BEM 230A</a>: Employment And/Or Self-Sufficiency Related Activities: Fip<ol>
<li>Citation #1 (score: 0.93)</li>
</ol></li>
</ul>"""
    )

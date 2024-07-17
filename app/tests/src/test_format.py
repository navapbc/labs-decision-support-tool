from sqlalchemy import delete

from src.db.models.document import Document
from src.format import format_guru_cards
from src.retrieve import retrieve_with_scores
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory
from tests.src.test_retrieve import _get_chunks


def _get_chunks_with_scores(db_session):
    db_session.execute(delete(Document))
    mock_embedding_model = MockSentenceTransformer()
    _get_chunks()
    return retrieve_with_scores(db_session, mock_embedding_model, "Very tiny words.", k=2)


def test_format_guru_cards_with_score(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    chunks = _get_chunks_with_scores(db_session)
    html = format_guru_cards(chunks)
    assert "accordion-1" in html
    assert "Related Guru cards" in html
    assert chunks[0][0].document.name in html
    assert chunks[0][0].document.content in html
    assert chunks[1][0].document.name in html
    assert chunks[1][0].document.content in html
    assert "Similarity Score" in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(chunks)
    assert "accordion-1" not in next_html
    assert "accordion-4" in next_html


def test_format_guru_cards_without_score(db_session):
    db_session.execute(delete(Document))
    chunks = ChunkFactory.build_batch(3)
    html = format_guru_cards(chunks, response_format="without_score")
    assert "accordion-1" not in html
    assert "accordion-4" not in html
    assert "Related Guru cards" in html
    assert "Similarity Score" not in html

    assert chunks[0].document.name in html
    assert chunks[0].document.content in html
    assert chunks[1].document.name in html
    assert chunks[1].document.content in html
    assert chunks[2].document.name in html
    assert chunks[2].document.content in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(chunks, response_format="without_score")
    assert "accordion-8" in next_html
    assert "accordion-9" in next_html

from sqlalchemy import delete

from src.db.models.document import Document
from src.format import format_guru_cards
from src.retrieve import retrieve_with_scores
from tests.src.test_retrieve import _create_chunks


def _get_chunks_with_scores():
    _create_chunks()
    return retrieve_with_scores("Very tiny words.", k=2)


# def mock_app_config(db_session):
#     class MockAppConfig:
#         def db_session(self):
#             print("==============MockAppConfig.db_session")
#             return db_session
#     return lambda: MockAppConfig()


def test_format_guru_cards_with_score(monkeypatch, app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    # monkeypatch.setattr(shared, "get_app_config", mock_app_config(db_session)) # TODO: get app_config from conftest.py and/or set db_session in shared.app_config
    chunks_with_scores = _get_chunks_with_scores()
    html = format_guru_cards(chunks_with_scores)
    assert "accordion-1" in html
    assert "Related Guru cards" in html
    assert chunks_with_scores[0].chunk.document.name in html
    assert chunks_with_scores[0].chunk.document.content in html
    assert chunks_with_scores[1].chunk.document.name in html
    assert chunks_with_scores[1].chunk.document.content in html
    assert "Similarity Score" in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(chunks_with_scores)
    assert "accordion-1" not in next_html
    assert "accordion-4" in next_html

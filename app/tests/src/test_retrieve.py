from sqlalchemy import delete

from src.db.models.document import Document
from src.retrieve import retrieve, retrieve_with_scores
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory


def _get_chunks():
    return [
        ChunkFactory.create(
            content="Incomprehensibility characterizes unintelligible, overwhelmingly convoluted dissertations."
        ),
        ChunkFactory.create(
            content="Curiosity inspires creative, innovative communities worldwide."
        ),
        ChunkFactory.create(content="The quick brown red fox jumps."),
    ]


def test_retrieve(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    mock_embedding_model = MockSentenceTransformer()
    _, medium_chunk, short_chunk = _get_chunks()

    results = retrieve(db_session, mock_embedding_model, "Very tiny words.", k=2)

    assert results == [short_chunk, medium_chunk]


def test_retrieve_with_scores(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    mock_embedding_model = MockSentenceTransformer()
    _, medium_chunk, short_chunk = _get_chunks()

    results = retrieve_with_scores(db_session, mock_embedding_model, "Very tiny words.", k=2)

    assert len(results) == 2
    assert results[0][0] == short_chunk
    assert results[0][1] == -0.7071067690849304
    assert results[1][0] == medium_chunk
    assert results[1][1] == -0.25881901383399963

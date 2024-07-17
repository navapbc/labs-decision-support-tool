import pytest
from sqlalchemy import delete

from src.db.models.document import Document
from src.retrieve import retrieve, retrieve_with_scores
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory, DocumentFactory

mock_embedding_model = MockSentenceTransformer()


def _create_chunks(document=None):
    if not document:
        document = DocumentFactory.create()
    return [
        ChunkFactory.create(
            document=document,
            content="Incomprehensibility characterizes unintelligible, overwhelmingly convoluted dissertations.",
        ),
        ChunkFactory.create(
            document=document,
            content="Curiosity inspires creative, innovative communities worldwide.",
        ),
        ChunkFactory.create(document=document, content="The quick brown red fox jumps."),
    ]


def test_retrieve(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _, medium_chunk, short_chunk = _create_chunks()

    results = retrieve(db_session, mock_embedding_model, "Very tiny words.", k=2)

    assert results == [short_chunk, medium_chunk]


def test_retrieve__with_empty_filter(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _, medium_chunk, short_chunk = _create_chunks()

    results = retrieve(db_session, mock_embedding_model, "Very tiny words.", k=2, datasets=[])

    assert results == [short_chunk, medium_chunk]


def test_retrieve__with_unknown_filter(db_session, enable_factory_create):
    with pytest.raises(ValueError):
        retrieve(
            db_session, mock_embedding_model, "Very tiny words.", k=2, unknown_column=["some value"]
        )


def test_retrieve__with_dataset_filter(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _create_chunks(document=DocumentFactory.create())
    _, snap_medium_chunk, snap_short_chunk = _create_chunks(
        document=DocumentFactory.create(dataset="my_very_unique_dataset")
    )

    results = retrieve(
        db_session,
        mock_embedding_model,
        "Very tiny words.",
        k=2,
        datasets=["my_very_unique_dataset"],
    )
    assert results == [snap_short_chunk, snap_medium_chunk]


def test_retrieve__with_other_filters(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _create_chunks(document=DocumentFactory.create(program="Medicaid", region="PA"))
    _, snap_medium_chunk, snap_short_chunk = _create_chunks(
        document=DocumentFactory.create(program="SNAP", region="MI")
    )

    results = retrieve(
        db_session,
        mock_embedding_model,
        "Very tiny words.",
        k=2,
        programs=["SNAP"],
        regions=["MI"],
    )
    assert results == [snap_short_chunk, snap_medium_chunk]


def test_retrieve_with_scores(db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _, medium_chunk, short_chunk = _create_chunks()

    results = retrieve_with_scores(db_session, mock_embedding_model, "Very tiny words.", k=2)

    assert len(results) == 2
    assert results[0][0] == short_chunk
    assert results[0][1] == -0.7071067690849304
    assert results[1][0] == medium_chunk
    assert results[1][1] == -0.25881901383399963

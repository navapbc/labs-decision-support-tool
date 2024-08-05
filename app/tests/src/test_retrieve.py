import pytest
from sqlalchemy import delete

from src.db.models.document import Document
from src.retrieve import retrieve_with_scores
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


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


def _format_retrieval_results(retrieval_results):
    return [chunk_with_score.chunk for chunk_with_score in retrieval_results]


def test_retrieve__with_empty_filter(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _, medium_chunk, short_chunk = _create_chunks()

    results = retrieve_with_scores(
        "Very tiny words.", retrieval_k=2, retrieval_k_min_score=0.0, datasets=[]
    )
    assert _format_retrieval_results(results) == [short_chunk, medium_chunk]


def test_retrieve__with_unknown_filter(app_config, db_session, enable_factory_create):
    with pytest.raises(ValueError):
        retrieve_with_scores(
            "Very tiny words.",
            retrieval_k=2,
            retrieval_k_min_score=0.0,
            unknown_column=["some value"],
        )


def test_retrieve__with_dataset_filter(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _create_chunks(document=DocumentFactory.create())
    _, snap_medium_chunk, snap_short_chunk = _create_chunks(
        document=DocumentFactory.create(dataset="SNAP")
    )

    results = retrieve_with_scores(
        "Very tiny words.",
        retrieval_k=2,
        retrieval_k_min_score=0.0,
        datasets=["SNAP"],
    )
    assert _format_retrieval_results(results) == [snap_short_chunk, snap_medium_chunk]


def test_retrieve__with_other_filters(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _create_chunks(document=DocumentFactory.create(program="Medicaid", region="PA"))
    _, snap_medium_chunk, snap_short_chunk = _create_chunks(
        document=DocumentFactory.create(program="SNAP", region="MI")
    )

    results = retrieve_with_scores(
        "Very tiny words.",
        retrieval_k=2,
        retrieval_k_min_score=0.0,
        programs=["SNAP"],
        regions=["MI"],
    )
    assert _format_retrieval_results(results) == [snap_short_chunk, snap_medium_chunk]


def test_retrieve_with_scores(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    _, medium_chunk, short_chunk = _create_chunks()

    results = retrieve_with_scores("Very tiny words.", retrieval_k=2, retrieval_k_min_score=0.0)

    assert len(results) == 2
    assert results[0].chunk == short_chunk
    assert results[0].score == 0.7071067690849304
    assert results[1].chunk == medium_chunk
    assert results[1].score == 0.25881901383399963

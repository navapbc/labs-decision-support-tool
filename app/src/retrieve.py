import logging
from typing import Sequence, Tuple

from sentence_transformers import SentenceTransformer
from sqlalchemy import Row, select

import src.adapters.db as db
from src.db.models.document import Chunk, Document

logger = logging.getLogger(__name__)


def retrieve(
    db_session: db.Session,
    embedding_model: SentenceTransformer,
    query: str,
    k: int = 5,
    **filters: Sequence | None,
) -> Sequence[Chunk]:
    chunks_with_scores = retrieve_with_scores(db_session, embedding_model, query, k, **filters)
    return [chunk for chunk, _ in chunks_with_scores]


def retrieve_with_scores(
    db_session: db.Session,
    embedding_model: SentenceTransformer,
    query: str,
    k: int = 5,
    **filters: Sequence | None,
) -> Sequence[Row[Tuple[Chunk, float]]]:
    logger.info("Retrieving context for %r", query)

    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    statement = select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding)).join(
        Chunk.document
    )
    if benefit_dataset := filters.pop("datasets", None):
        statement = statement.filter(Document.dataset.in_(benefit_dataset))
    if benefit_programs := filters.pop("programs", None):
        statement = statement.filter(Document.program.in_(benefit_programs))
    if benefit_regions := filters.pop("regions", None):
        statement = statement.filter(Document.region.in_(benefit_regions))

    if filters:
        raise ValueError(f"Unknown filters: {filters.keys()}")

    chunks_with_scores = db_session.execute(
        statement.order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(k)
    ).all()

    for chunk, score in chunks_with_scores:
        logger.info(f"Retrieved: {chunk.document.name!r} with score {score}")

    return chunks_with_scores

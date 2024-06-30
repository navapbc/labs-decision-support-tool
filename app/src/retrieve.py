import logging
from typing import Sequence, Tuple

from sentence_transformers import SentenceTransformer
from sqlalchemy import Row, select

import src.adapters.db as db
from src.db.models.document import Chunk

logger = logging.getLogger(__name__)


def retrieve(
    db_session: db.Session, embedding_model: SentenceTransformer, query: str, k: int = 5
) -> Sequence[Chunk]:
    logger.info(f"Retrieving context for {query!r}")

    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    chunks = db_session.scalars(
        select(Chunk).order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(k)
    ).all()

    for chunk in chunks:
        logger.info(f"Retrieved: {chunk.document.name!r}")

    return chunks


def retrieve_with_scores(
    db_session: db.Session, embedding_model: SentenceTransformer, query: str, k: int = 5
) -> Sequence[Row[Tuple[Chunk, float]]]:
    logger.info(f"Retrieving context for {query!r}")

    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    chunks_with_scores = db_session.execute(
        select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .limit(k)
    ).all()

    for chunk, score in chunks_with_scores:
        logger.info(f"Retrieved: {chunk.document.name!r} with score {score}")

    return chunks_with_scores

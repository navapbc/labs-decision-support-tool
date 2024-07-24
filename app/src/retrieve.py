import logging
from typing import Sequence

from sqlalchemy import select

from src.app_config import app_config
from src.db.models.document import Chunk, ChunkWithScore, Document

logger = logging.getLogger(__name__)


def retrieve_with_scores(
    query: str,
    k: int = 5,
    **filters: Sequence[str] | None,
) -> Sequence[ChunkWithScore]:
    logger.info("Retrieving context for %r", query)

    embedding_model = app_config.sentence_transformer
    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    statement = select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding)).join(
        Chunk.document
    )
    if benefit_dataset := filters.pop("datasets", None):
        statement = statement.where(Document.dataset.in_(benefit_dataset))
    if benefit_programs := filters.pop("programs", None):
        statement = statement.where(Document.program.in_(benefit_programs))
    if benefit_regions := filters.pop("regions", None):
        statement = statement.where(Document.region.in_(benefit_regions))

    if filters:
        raise ValueError(f"Unknown filters: {filters.keys()}")

    with app_config.db_session() as db_session:
        chunks_with_scores = db_session.execute(
            statement.order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(k)
        ).all()

        for chunk, score in chunks_with_scores:
            logger.info(f"Retrieved: {chunk.document.name!r} with score {score}")

        return [ChunkWithScore(chunk, score) for chunk, score in chunks_with_scores]

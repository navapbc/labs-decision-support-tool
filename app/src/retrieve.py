import logging
from typing import Sequence

from sqlalchemy import select

from src.app_config import app_config
from src.db.models.document import Chunk, ChunkWithScore, Document

logger = logging.getLogger(__name__)


def retrieve_with_scores(
    query: str,
    k: int = app_config.retrieval_k,
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
        # Confirmed that the `max_inner_product` method returns the same score as using sentence_transformers.util.dot_score
        # used in code at https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1
        chunks_with_scores = db_session.execute(
            statement.order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(k)
        ).all()

        retrievals = [
            f"{index}. score {-score:.4f}: {chunk.document.name!r}"
            for index, (chunk, score) in enumerate(chunks_with_scores, start=1)
        ]
        logger.info("Retrieved %d docs:\n  %s", len(chunks_with_scores), "\n  ".join(retrievals))

        # Scores from the DB query are negated, presumably to reverse the default sort order
        filtered_chunks_with_scores = [
            ChunkWithScore(chunk, -score)
            for chunk, score in chunks_with_scores
            if -score >= app_config.retrieval_k_min_score
        ]
        if len(filtered_chunks_with_scores) < len(chunks_with_scores):
            logger.info(
                "Keeping only the top %d, which meet the %f score threshold.",
                len(filtered_chunks_with_scores),
                app_config.retrieval_k_min_score,
            )

        return filtered_chunks_with_scores

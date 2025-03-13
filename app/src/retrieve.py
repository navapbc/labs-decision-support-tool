import logging
from typing import Sequence

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from src.app_config import app_config
from src.db.models.document import Chunk, ChunkWithScore, Document
from src.profiling import profile_function, add_metadata

logger = logging.getLogger(__name__)


def analyze_query_plan(db_session: Session, statement) -> None:
    """Analyze and log the query execution plan."""
    # Convert SQLAlchemy statement to raw SQL
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    
    # Get the query plan
    explain_results = db_session.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
    ).scalar()
    
    # Extract key metrics from the plan
    plan = explain_results[0]["Plan"]
    add_metadata("query_planning_time", explain_results[0]["Planning Time"])
    add_metadata("query_execution_time", explain_results[0]["Execution Time"])
    
    # Track index usage
    if "Index Scan" in plan["Node Type"]:
        add_metadata("index_name", plan["Index Name"])
        add_metadata("index_scan_direction", plan.get("Scan Direction", "Forward"))
    
    # Track I/O statistics
    shared_hit_blocks = plan.get("Shared Hit Blocks", 0)
    shared_read_blocks = plan.get("Shared Read Blocks", 0)
    if shared_hit_blocks + shared_read_blocks > 0:
        cache_hit_ratio = shared_hit_blocks / (shared_hit_blocks + shared_read_blocks)
        add_metadata("cache_hit_ratio", cache_hit_ratio)
    
    logger.debug("Query plan: %s", explain_results)


@profile_function("vector_search")
def retrieve_with_scores(
    query: str,
    retrieval_k: int,
    retrieval_k_min_score: float,
    **filters: Sequence[str] | None,
) -> list[ChunkWithScore]:
    """
    Returns a list of ChunkWithScore objects, sorted by relevance score.
    """
    logger.info("Retrieving context for %r", query)

    # Get embeddings for query
    embedding_model = app_config.sentence_transformer
    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    # Build query
    statement = select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding)).join(
        Chunk.document
    )

    # Apply filters
    if benefit_dataset := filters.pop("datasets", None):
        statement = statement.where(Document.dataset.in_(benefit_dataset))
    if benefit_programs := filters.pop("programs", None):
        statement = statement.where(Document.program.in_(benefit_programs))
    if benefit_regions := filters.pop("regions", None):
        statement = statement.where(Document.region.in_(benefit_regions))

    if filters:
        raise ValueError(f"Unknown filters: {filters.keys()}")

    with app_config.db_session() as db_session:
        # Analyze query plan before execution
        analyze_query_plan(db_session, statement)
        
        # Confirmed that the `max_inner_product` method returns the same score as using sentence_transformers.util.dot_score
        # used in code at https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1
        chunks_with_scores = db_session.execute(
            statement.order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(
                retrieval_k
            )
        ).all()
        
        # Add metadata about search results
        add_metadata("num_chunks_retrieved", len(chunks_with_scores))
        add_metadata("min_score", min(r[1] for r in chunks_with_scores) if chunks_with_scores else None)
        add_metadata("max_score", max(r[1] for r in chunks_with_scores) if chunks_with_scores else None)
        add_metadata("avg_score", sum(r[1] for r in chunks_with_scores) / len(chunks_with_scores) if chunks_with_scores else None)

        # Add detailed logging about chunks and their scores
        logger.info("Retrieved %d chunks with scores:", len(chunks_with_scores))
        for i, (chunk, score) in enumerate(chunks_with_scores, 1):
            logger.info(
                "Chunk %d/%d:\n  ID: %s\n  Score: %.4f\n  Document: %r\n  Content Preview: %.100s...",
                i, len(chunks_with_scores),
                chunk.id,
                -score,  # Negate score back to original value
                chunk.document.name,
                chunk.content[:100]
            )

        retrievals = [
            f"{index}. score {-score:.4f}: {chunk.id}, {chunk.document.name!r}"
            for index, (chunk, score) in enumerate(chunks_with_scores, start=1)
        ]
        logger.info("Retrieved %d docs:\n  %s", len(chunks_with_scores), "\n  ".join(retrievals))

        # Scores from the DB query are negated, presumably to reverse the default sort order
        filtered_chunks_with_scores = [
            ChunkWithScore(chunk, -score)
            for chunk, score in chunks_with_scores
            if -score >= retrieval_k_min_score
        ]
        if len(filtered_chunks_with_scores) < len(chunks_with_scores):
            logger.info(
                "Keeping only the top %d, which meet the %f score threshold.",
                len(filtered_chunks_with_scores),
                retrieval_k_min_score,
            )

        return filtered_chunks_with_scores

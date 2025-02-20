"""Results processing for evaluation runs."""

from hashlib import md5
from typing import Any, Dict, List

from src.app_config import app_config
from src.db.models.document import Chunk

from ..data_models import EvaluationResult, ExpectedChunk, RetrievedChunk
from ..utils.id_generator import generate_stable_id
from ..utils.progress import ProgressTracker
from ..utils.timer import measure_time


def generate_qa_pair_id(question: str, answer: str, dataset: str) -> str:
    """Generate a stable UUID for a QA pair based on content.

    The QA Pair UUID will be deterministic based on question, answer, and dataset.
    So it will be consistent between runs but will change if the content changes.

    Args:
        question: The question text
        answer: The expected answer text
        dataset: The dataset identifier (e.g., "imagine_la")

    Returns:
        UUID string stable on QA and dataset content
    """
    # For backwards compatibility, include dataset in the hash
    answer_with_dataset = f"{answer}||{dataset}"
    return str(generate_stable_id(question, answer_with_dataset))


def process_retrieved_chunks(
    question: Dict[str, Any], retrieved_chunks: List[Any], retrieval_time_ms: float
) -> EvaluationResult:
    """Process retrieved chunks for a question.

    Args:
        question: Question dictionary with metadata
        retrieved_chunks: List of retrieved chunks with scores
        retrieval_time_ms: Time taken for retrieval in ms

    Returns:
        EvaluationResult object
    """
    # Get expected chunk content from database
    expected_chunk_id = question.get("chunk_id", "")
    expected_chunk_content = ""
    if expected_chunk_id:
        with app_config.db_session() as session:
            chunk = session.query(Chunk).filter(Chunk.id == expected_chunk_id).first()
            if chunk:
                expected_chunk_content = chunk.content

    # Extract document info
    expected_chunk = ExpectedChunk(
        name=question.get("document_name", ""),
        source=question.get("dataset", ""),
        chunk_id=expected_chunk_id,
        content_hash=question.get("content_hash", ""),
        content=expected_chunk_content,
    )

    # Process retrieved chunks
    processed_chunks = []
    content_hashes = []

    for chunk in retrieved_chunks:
        if not chunk or not hasattr(chunk, "chunk") or not hasattr(chunk, "score"):
            continue

        chunk_obj = chunk.chunk
        if not chunk_obj or not hasattr(chunk_obj, "content") or not hasattr(chunk_obj, "id"):
            continue

        content = chunk_obj.content
        content_hash = md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()
        content_hashes.append(content_hash)

        processed_chunks.append(
            RetrievedChunk(
                chunk_id=str(chunk_obj.id),
                score=chunk.score,
                content=content,
                content_hash=content_hash,
            )
        )

    # Check if correct chunk was found
    correct_chunk_retrieved = expected_chunk.content_hash in content_hashes

    # Find rank if found
    rank_if_found = None
    if correct_chunk_retrieved:
        rank_if_found = content_hashes.index(expected_chunk.content_hash) + 1

    # Generate a stable UUID for this QA pair if one isn't provided
    qa_pair_id = question.get("id") or generate_qa_pair_id(
        question=question["question"],
        answer=question.get("answer", ""),
        dataset=expected_chunk.source,
    )

    return EvaluationResult(
        qa_pair_id=qa_pair_id,
        question=question["question"],
        expected_answer=question.get("answer", ""),
        expected_chunk=expected_chunk,
        correct_chunk_retrieved=correct_chunk_retrieved,
        rank_if_found=rank_if_found,
        retrieval_time_ms=retrieval_time_ms,
        retrieved_chunks=processed_chunks,
        dataset=question.get("dataset", ""),
    )


def batch_process_results(
    questions: List[Dict], retrieval_func: Any, k: int
) -> List[EvaluationResult]:
    """Process multiple questions in batches.

    Args:
        questions: List of questions to process
        retrieval_func: Function to retrieve chunks for a question
        k: Number of chunks to retrieve

    Returns:
        List of EvaluationResult objects
    """
    results = []
    progress = ProgressTracker("Evaluation")

    # Process each question individually to avoid pgvector batch issues
    with measure_time() as timer:
        # Process in database session
        with app_config.db_session():
            for question in progress.track_items(questions, "Processing questions"):
                query = question["question"]
                retrieved = retrieval_func(query, k)

                # Process results
                retrieval_time = timer.elapsed_ms() / len(questions)  # Average time per question
                results.append(process_retrieved_chunks(question, retrieved, retrieval_time))

    # Log completion stats
    progress.log_completion(
        {
            "Questions processed": len(questions),
            "Average retrieval time (ms)": timer.elapsed_ms() / len(questions),
            "items_processed": len(questions),
        }
    )

    return results

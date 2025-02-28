"""Results processing for evaluation runs."""

from hashlib import md5
from typing import Dict, List, Sequence

from tqdm import tqdm

from src.db.models.document import ChunkWithScore
from src.evaluation.data_models import EvaluationResult, ExpectedChunk, RetrievedChunk
from src.retrieve import retrieve_with_scores

from ..utils.timer import measure_time


def process_retrieved_chunks(
    question: Dict[str, str], retrieved_chunks: Sequence[ChunkWithScore], retrieval_time_ms: float
) -> EvaluationResult:
    """Process retrieved chunks for a question.

    Args:
        question: Question dictionary with metadata
        retrieved_chunks: List of retrieved chunks with scores from retrieve_with_scores
        retrieval_time_ms: Time taken for retrieval in ms

    Returns:
        EvaluationResult object

    Raises:
        ValueError: If the question dictionary is missing required fields
    """
    # Validate required fields
    if "id" not in question:
        raise ValueError("Question dictionary must contain an 'id' field")

    # Extract document info
    expected_chunk = ExpectedChunk(
        name=question.get("document_name", ""),
        source=question.get("dataset", ""),
        chunk_id=question.get("chunk_id", ""),
        content_hash=question.get("content_hash", ""),
        content=question.get("expected_chunk_content", ""),
    )

    # Process retrieved chunks
    processed_chunks = []
    content_hashes = []

    for chunk in retrieved_chunks:
        content = chunk.chunk.content
        content_hash = md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()
        content_hashes.append(content_hash)

        processed_chunks.append(
            RetrievedChunk(
                chunk_id=str(chunk.chunk.id),
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

    return EvaluationResult(
        qa_pair_id=question["id"],
        question=question["question"],
        expected_answer=question.get("answer", ""),
        expected_chunk=expected_chunk,
        correct_chunk_retrieved=correct_chunk_retrieved,
        rank_if_found=rank_if_found,
        retrieval_time_ms=retrieval_time_ms,
        retrieved_chunks=processed_chunks,
        dataset=expected_chunk.source,
    )


def batch_process_results(questions: List[Dict], k: int) -> List[EvaluationResult]:
    """Process multiple questions in batches.

    Args:
        questions: List of questions to process
        k: Number of chunks to retrieve

    Returns:
        List of EvaluationResult objects
    """
    results = []

    with measure_time() as timer:
        for question in tqdm(questions, desc="Processing questions"):
            # Get chunks with scores using positional args to match test expectations
            retrieved = retrieve_with_scores(question["question"], k, retrieval_k_min_score=0.0)

            # Process results
            retrieval_time = timer.elapsed_ms() / len(questions)  # Average time per question
            result = process_retrieved_chunks(question, retrieved, retrieval_time)
            results.append(result)

    return results

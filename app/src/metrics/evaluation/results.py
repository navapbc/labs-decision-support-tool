"""Results processing for evaluation runs."""

from hashlib import md5
from typing import Any, Dict, List

from tqdm import tqdm

from src.app_config import app_config

from ..models.metrics import DocumentInfo, EvaluationResult, RetrievedChunk
from ..utils.timer import measure_time


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
    # Extract document info
    doc_info = DocumentInfo(
        name=question.get("document_name", ""),
        source=question.get("dataset", ""),
        chunk_id=question.get("chunk_id", ""),
        content_hash=question.get("content_hash", ""),
    )

    # Process retrieved chunks
    processed_chunks = []
    content_hashes = []
    scores = []

    for chunk in retrieved_chunks:
        content = chunk.chunk.content
        content_hash = md5(content.encode("utf-8")).hexdigest()
        content_hashes.append(content_hash)
        scores.append(chunk.score)

        processed_chunks.append(
            RetrievedChunk(chunk_id=str(chunk.chunk.id), score=chunk.score, content=content)
        )

    # Check if correct chunk was found
    correct_chunk_retrieved = doc_info.content_hash in content_hashes

    # Find rank if found
    rank_if_found = None
    if correct_chunk_retrieved:
        rank_if_found = content_hashes.index(doc_info.content_hash) + 1

    return EvaluationResult(
        qa_pair_id=question.get("id", ""),
        question=question["question"],
        expected_answer=question.get("answer", ""),
        document_info=doc_info,
        correct_chunk_retrieved=correct_chunk_retrieved,
        rank_if_found=rank_if_found,
        top_k_scores=scores,
        retrieval_time_ms=retrieval_time_ms,
        retrieved_chunks=processed_chunks,
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

    # Process each question individually to avoid pgvector batch issues
    with measure_time() as t:  # Use a different variable name
        # Process in database session
        with app_config.db_session():
            for question in tqdm(questions, desc="Processing questions"):
                query = question["question"]
                retrieved = retrieval_func(query, k)

                # Process results
                retrieval_time = t.elapsed_ms() / len(questions)  # Average time per question
                result = process_retrieved_chunks(question, retrieved, retrieval_time)
                results.append(result)

    return results

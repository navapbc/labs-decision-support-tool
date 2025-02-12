"""Tests for evaluation results processing."""

from unittest.mock import MagicMock, patch

import pytest

from src.metrics.evaluation.results import batch_process_results, process_retrieved_chunks
from src.metrics.models.metrics import DocumentInfo, EvaluationResult, RetrievedChunk


@pytest.fixture
def mock_question():
    """Create a mock question dictionary."""
    return {
        "id": "test_id",
        "question": "test question?",
        "answer": "test answer",
        "document_name": "test_doc",
        "dataset": "test_dataset",
        "chunk_id": "chunk_123",
        "content_hash": "abc123",
    }


@pytest.fixture
def mock_chunk():
    """Create a mock chunk with content."""
    chunk = MagicMock()
    chunk.chunk.id = "chunk_123"
    chunk.chunk.content = "test content"
    chunk.score = 0.85
    return chunk


def test_process_retrieved_chunks_found(mock_question, mock_chunk):
    """Test processing retrieved chunks when correct chunk is found."""
    # Create a list of retrieved chunks where the first one matches
    mock_chunk.chunk.content = (
        "matching content"  # This will generate the same hash as mock_question
    )
    retrieved_chunks = [mock_chunk]

    # Mock the md5 hash to match the expected hash
    with patch("src.metrics.evaluation.results.md5") as mock_md5:
        mock_md5.return_value.hexdigest.return_value = mock_question["content_hash"]

        result = process_retrieved_chunks(mock_question, retrieved_chunks, 100.5)

        # Verify result
        assert isinstance(result, EvaluationResult)
        assert result.qa_pair_id == mock_question["id"]
        assert result.question == mock_question["question"]
        assert result.expected_answer == mock_question["answer"]
        assert result.correct_chunk_retrieved is True
        assert result.rank_if_found == 1
        assert result.top_k_scores == [0.85]
        assert result.retrieval_time_ms == 100.5

        # Verify document info
        assert isinstance(result.document_info, DocumentInfo)
        assert result.document_info.name == mock_question["document_name"]
        assert result.document_info.source == mock_question["dataset"]
        assert result.document_info.chunk_id == mock_question["chunk_id"]
        assert result.document_info.content_hash == mock_question["content_hash"]

        # Verify retrieved chunks
        assert len(result.retrieved_chunks) == 1
        chunk = result.retrieved_chunks[0]
        assert isinstance(chunk, RetrievedChunk)
        assert chunk.chunk_id == str(mock_chunk.chunk.id)
        assert chunk.score == mock_chunk.score
        assert chunk.content == mock_chunk.chunk.content


def test_process_retrieved_chunks_not_found(mock_question, mock_chunk):
    """Test processing retrieved chunks when correct chunk is not found."""
    # Create a list of retrieved chunks where none match
    retrieved_chunks = [mock_chunk]

    result = process_retrieved_chunks(mock_question, retrieved_chunks, 100.5)

    # Verify result
    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None
    assert result.top_k_scores == [0.85]


def test_process_retrieved_chunks_empty():
    """Test processing retrieved chunks with empty input."""
    question = {
        "id": "test_id",
        "question": "test question?",
    }
    retrieved_chunks = []

    result = process_retrieved_chunks(question, retrieved_chunks, 100.5)

    # Verify result
    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None
    assert result.top_k_scores == []
    assert result.document_info.name == ""
    assert result.document_info.source == ""
    assert result.document_info.chunk_id == ""
    assert result.document_info.content_hash == ""


def test_batch_process_results(mock_question, mock_chunk):
    """Test batch processing of results."""
    questions = [mock_question]
    k = 1

    # Mock retrieval function
    def mock_retrieval_func(query: str, k: int):
        return [mock_chunk]

    # Mock app_config.db_session context manager
    with patch("src.metrics.evaluation.results.app_config") as mock_config:
        mock_config.db_session.return_value.__enter__.return_value = None
        mock_config.db_session.return_value.__exit__.return_value = None

        # Mock measure_time context manager
        with patch("src.metrics.evaluation.results.measure_time") as mock_timer:
            mock_timer.return_value.__enter__.return_value.elapsed_ms.return_value = 100.5

            results = batch_process_results(questions, mock_retrieval_func, k)

            # Verify results
            assert len(results) == 1
            assert isinstance(results[0], EvaluationResult)
            assert results[0].question == mock_question["question"]
            assert results[0].retrieval_time_ms == 100.5

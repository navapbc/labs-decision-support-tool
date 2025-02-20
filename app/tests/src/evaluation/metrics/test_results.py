"""Tests for evaluation results processing."""

from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.data_models import EvaluationResult, ExpectedChunk, RetrievedChunk
from src.evaluation.metrics.results import batch_process_results, process_retrieved_chunks
from src.evaluation.utils.id_generator import generate_stable_id


def test_generate_stable_id():
    """Test UUID generation for QA pairs."""
    # Test that same inputs generate same UUID
    uuid1 = str(generate_stable_id("test question?", "test answer"))
    uuid2 = str(generate_stable_id("test question?", "test answer"))
    assert uuid1 == uuid2

    # Test that different inputs generate different UUIDs
    uuid3 = str(generate_stable_id("different question?", "test answer"))
    assert uuid1 != uuid3

    uuid4 = str(generate_stable_id("test question?", "different answer"))
    assert uuid1 != uuid4


@pytest.fixture
def mock_question():
    """Create a mock question dictionary."""
    return {
        "id": "test_id",
        "question": "test question?",
        "answer": "test answer",
        "document_name": "test_doc",
        "dataset": "test_dataset",
        "chunk_id": "123e4567-e89b-12d3-a456-426614174000",
        "content_hash": "abc123",
    }


@pytest.fixture
def mock_question_no_id(mock_question):
    """Create a mock question dictionary without an ID."""
    question = mock_question.copy()
    del question["id"]
    return question


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
    mock_chunk.chunk.id = mock_question["chunk_id"]  # Match the chunk ID
    mock_chunk.chunk.content = (
        "matching content"  # This will generate the same hash as mock_question
    )
    mock_chunk.score = 0.85
    retrieved_chunks = [mock_chunk]

    # Mock the md5 hash to match the expected hash
    with patch("src.evaluation.metrics.results.md5") as mock_md5:
        mock_md5.return_value.hexdigest.return_value = mock_question["content_hash"]

        result = process_retrieved_chunks(mock_question, retrieved_chunks, 100.5)

        # Verify result
        assert isinstance(result, EvaluationResult)
        assert result.qa_pair_id == mock_question["id"]
        assert result.question == mock_question["question"]
        assert result.expected_answer == mock_question["answer"]
        assert result.correct_chunk_retrieved is True
        assert result.rank_if_found == 1
        assert result.retrieval_time_ms == 100.5

        # Verify expected chunk
        assert isinstance(result.expected_chunk, ExpectedChunk)
        assert result.expected_chunk.name == mock_question["document_name"]
        assert result.expected_chunk.source == mock_question["dataset"]
        assert result.expected_chunk.chunk_id == mock_question["chunk_id"]
        assert result.expected_chunk.content_hash == mock_question["content_hash"]

        # Verify retrieved chunks
        assert len(result.retrieved_chunks) == 1
        chunk = result.retrieved_chunks[0]
        assert isinstance(chunk, RetrievedChunk)
        assert chunk.chunk_id == str(mock_chunk.chunk.id)
        assert chunk.score == mock_chunk.score
        assert chunk.content == mock_chunk.chunk.content


def test_process_retrieved_chunks_no_id(mock_question_no_id, mock_chunk):
    """Test processing retrieved chunks when no ID is provided."""
    retrieved_chunks = [mock_chunk]

    result = process_retrieved_chunks(mock_question_no_id, retrieved_chunks, 100.5)

    # Verify a UUID was generated
    assert result.qa_pair_id != ""
    # Verify it's stable for same inputs
    result2 = process_retrieved_chunks(mock_question_no_id, retrieved_chunks, 100.5)
    assert result.qa_pair_id == result2.qa_pair_id


def test_process_retrieved_chunks_not_found(mock_question, mock_chunk):
    """Test processing retrieved chunks when correct chunk is not found."""
    # Create a list of retrieved chunks where none match
    retrieved_chunks = [mock_chunk]

    result = process_retrieved_chunks(mock_question, retrieved_chunks, 100.5)

    # Verify result
    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None
    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].score == 0.85


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
    assert len(result.retrieved_chunks) == 0
    assert result.expected_chunk.name == ""
    assert result.expected_chunk.source == ""
    assert result.expected_chunk.chunk_id == ""
    assert result.expected_chunk.content_hash == ""


def test_batch_process_results(mock_question, mock_chunk):
    """Test batch processing of results."""
    questions = [mock_question]
    k = 1

    # Mock retrieval function
    def mock_retrieval_func(query: str, k: int):
        return [mock_chunk]

    # Mock app_config.db_session and measure_time context managers
    with (
        patch("src.evaluation.metrics.results.app_config") as mock_config,
        patch("src.evaluation.metrics.results.measure_time") as mock_timer,
        patch("src.evaluation.metrics.results.md5") as mock_md5,
    ):
        # Setup mock database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_config.db_session.return_value.__enter__.return_value = mock_session
        mock_config.db_session.return_value.__exit__.return_value = None

        # Create a mock timer object with elapsed_ms as a method
        mock_timer_obj = MagicMock()
        mock_timer_obj.elapsed_ms.return_value = 100.5
        mock_timer.return_value.__enter__.return_value = mock_timer_obj

        mock_md5.return_value.hexdigest.return_value = mock_question["content_hash"]

        results = batch_process_results(questions, mock_retrieval_func, k)

        # Verify results
        assert len(results) == 1
        assert isinstance(results[0], EvaluationResult)
        assert results[0].question == mock_question["question"]
        assert (
            abs(results[0].retrieval_time_ms - 100.5) < 0.1
        )  # Allow small floating point difference

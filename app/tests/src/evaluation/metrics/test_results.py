"""Tests for evaluation results processing."""

import uuid
from collections import namedtuple
from hashlib import md5
from unittest.mock import patch

import pytest
from sqlalchemy import delete

from src.db.models.document import Document
from src.evaluation.metrics.results import batch_process_results, process_retrieved_chunks
from tests.src.db.models.factories import ChunkFactory, DocumentFactory

# Create mock version instead of importing from retrieve
MockChunkWithScore = namedtuple('MockChunkWithScore', ['chunk', 'score'])


@pytest.fixture
def question_dict():
    """Create a test question dictionary."""
    content = "test chunk content"
    return {
        "id": str(uuid.uuid4()),
        "question": "test question?",
        "answer": "test answer",
        "document_name": "test_doc",
        "dataset": "test_dataset",
        "chunk_id": "chunk_123",
        "content_hash": md5(content.encode("utf-8"), usedforsecurity=False).hexdigest(),
        "expected_chunk_content": content,
    }


def test_process_retrieved_chunks_found(question_dict, enable_factory_create, db_session):
    """Test processing retrieved chunks when correct chunk is found."""
    document = DocumentFactory.create(
        name=question_dict["document_name"],
        dataset=question_dict["dataset"],
    )
    chunk = ChunkFactory.create(
        document=document,
        content=question_dict["expected_chunk_content"],
    )
    retrieved_chunks = [MockChunkWithScore(chunk=chunk, score=0.85)]

    result = process_retrieved_chunks(question_dict, retrieved_chunks, 100.5)

    assert result.qa_pair_id == question_dict["id"]
    assert result.question == question_dict["question"]
    assert result.expected_answer == question_dict["answer"]
    assert result.correct_chunk_retrieved is True
    assert result.rank_if_found == 1
    assert result.retrieval_time_ms == 100.5


def test_process_retrieved_chunks_missing_id(question_dict, enable_factory_create, db_session):
    """Test that processing chunks with missing ID raises an error."""
    document = DocumentFactory.create()
    chunk = ChunkFactory.create(document=document)
    retrieved_chunks = [MockChunkWithScore(chunk=chunk, score=0.85)]

    del question_dict["id"]
    with pytest.raises(ValueError, match="Question dictionary must contain an 'id' field"):
        process_retrieved_chunks(question_dict, retrieved_chunks, 100.5)


def test_process_retrieved_chunks_not_found(question_dict, enable_factory_create, db_session):
    """Test processing retrieved chunks when correct chunk is not found."""
    document = DocumentFactory.create()
    chunk = ChunkFactory.create(document=document)
    retrieved_chunks = [MockChunkWithScore(chunk=chunk, score=0.85)]

    result = process_retrieved_chunks(question_dict, retrieved_chunks, 100.5)
    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None
    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].score == 0.85


def test_process_retrieved_chunks_empty():
    """Test processing retrieved chunks with empty input."""
    question = {
        "id": str(uuid.uuid4()),
        "question": "test question?",
    }
    result = process_retrieved_chunks(question, [], 100.5)
    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None
    assert len(result.retrieved_chunks) == 0


def test_batch_process_results(question_dict, enable_factory_create, db_session):
    """Test batch processing of results."""
    # Create our test document and chunk
    document = DocumentFactory.create(
        name=question_dict["document_name"],
        dataset=question_dict["dataset"],
    )
    chunk = ChunkFactory.create(
        document=document,
        content=question_dict["expected_chunk_content"],
    )

    # Update the question dict to match the created chunk
    question_dict["chunk_id"] = str(chunk.id)
    question_dict["content_hash"] = md5(
        chunk.content.encode("utf-8"), usedforsecurity=False
    ).hexdigest()

    # Mock retrieve_with_scores to return our chunk with a high score
    with patch("src.evaluation.metrics.results.retrieve_with_scores") as mock_retrieve:
        mock_retrieve.return_value = [MockChunkWithScore(chunk=chunk, score=0.95)]  # High score that passes threshold
        
        results = batch_process_results([question_dict], k=1)

        # Verify mock was called with correct parameters
        mock_retrieve.assert_called_once_with(
            question_dict["question"],
            1,  # k
            retrieval_k_min_score=0.0  # Use same threshold as retrieval tests
        )

        assert len(results) == 1
        result = results[0]

        # Verify all fields in EvaluationResult
        assert result.qa_pair_id == question_dict["id"]
        assert result.question == question_dict["question"]
        assert result.expected_answer == question_dict["answer"]
        assert result.dataset == question_dict["dataset"]
        assert result.retrieval_time_ms > 0
        assert result.correct_chunk_retrieved is True
        assert result.rank_if_found == 1

        # Verify expected chunk
        assert result.expected_chunk.name == question_dict["document_name"]
        assert result.expected_chunk.source == question_dict["dataset"]
        assert result.expected_chunk.chunk_id == question_dict["chunk_id"]
        assert result.expected_chunk.content_hash == question_dict["content_hash"]
        assert result.expected_chunk.content == question_dict["expected_chunk_content"]

        # Verify retrieved chunks
        assert len(result.retrieved_chunks) == 1
        retrieved_chunk = result.retrieved_chunks[0]
        assert retrieved_chunk.chunk_id == str(chunk.id)
        assert retrieved_chunk.content == chunk.content
        assert retrieved_chunk.content_hash == question_dict["content_hash"]

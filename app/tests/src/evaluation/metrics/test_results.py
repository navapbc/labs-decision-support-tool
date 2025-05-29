"""Tests for evaluation results processing."""

import uuid
from hashlib import md5

import pytest

from src.db.models.document import ChunkWithScore
from src.evaluation.data_models import EvaluationResult, ExpectedChunk, RetrievedChunk
from src.evaluation.metrics.results import (
    batch_process_results,
    generate_qa_pair_id,
    process_retrieved_chunks,
)
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


def test_generate_qa_pair_id():
    """Test UUID generation for QA pairs."""
    # Test that same inputs generate same UUID
    uuid1 = generate_qa_pair_id("test question?", "test answer", "test_dataset")
    uuid2 = generate_qa_pair_id("test question?", "test answer", "test_dataset")
    assert uuid1 == uuid2

    # Test that different inputs generate different UUIDs
    uuid3 = generate_qa_pair_id("different question?", "test answer", "test_dataset")
    assert uuid1 != uuid3

    uuid4 = generate_qa_pair_id("test question?", "different answer", "test_dataset")
    assert uuid1 != uuid4

    uuid5 = generate_qa_pair_id("test question?", "test answer", "different_dataset")
    assert uuid1 != uuid5


@pytest.fixture
def test_document():
    """Create a test document with a chunk."""
    document = DocumentFactory.build(
        name="test_doc",
        content="Test document content",
        source="test_dataset",
    )
    chunk = ChunkFactory.build(
        document=document,
        content="test chunk content",
        id=uuid.uuid4(),
    )
    document.chunks = [chunk]
    return document


@pytest.fixture
def test_question(test_document):
    """Create a test question dictionary from document."""
    chunk = test_document.chunks[0]
    content_hash = md5(chunk.content.encode("utf-8"), usedforsecurity=False).hexdigest()

    return {
        "id": str(uuid.uuid4()),
        "question": "test question?",
        "answer": "test answer",
        "document_name": test_document.name,
        "document_id": str(test_document.id),
        "dataset": test_document.dataset,
        "chunk_id": str(chunk.id),
        "content_hash": content_hash,
        "expected_chunk_content": chunk.content,
    }


def test_process_retrieved_chunks_found(test_document, test_question):
    """Test processing retrieved chunks when correct chunk is found."""
    chunk = test_document.chunks[0]
    retrieved_chunks = [ChunkWithScore(chunk=chunk, score=0.85)]

    result = process_retrieved_chunks(test_question, retrieved_chunks, 100.5)

    # Verify result
    assert isinstance(result, EvaluationResult)
    assert result.qa_pair_id == test_question["id"]
    assert result.question == test_question["question"]
    assert result.expected_answer == test_question["answer"]
    assert result.correct_chunk_retrieved is True
    assert result.rank_if_found == 1
    assert result.retrieval_time_ms == 100.5
    assert result.correct_document_retrieved is True
    assert result.document_rank_if_found == 1

    # Verify expected chunk
    assert isinstance(result.expected_chunk, ExpectedChunk)
    assert result.expected_chunk.name == test_question["document_name"]
    assert result.expected_chunk.source == test_question["dataset"]
    assert result.expected_chunk.chunk_id == test_question["chunk_id"]
    assert result.expected_chunk.content == test_question["expected_chunk_content"]
    assert result.expected_chunk.document_id == test_question["document_id"]

    # Verify retrieved chunks
    assert len(result.retrieved_chunks) == 1
    retrieved = result.retrieved_chunks[0]
    assert isinstance(retrieved, RetrievedChunk)
    assert retrieved.chunk_id == str(chunk.id)
    assert retrieved.score == 0.85
    assert retrieved.content == chunk.content
    assert retrieved.document_id == str(chunk.document_id)


def test_process_retrieved_chunks_not_found(test_document, test_question):
    """Test processing retrieved chunks when correct chunk is not found."""
    # Create a different chunk that won't match
    different_chunk = ChunkFactory.build(
        document=test_document,
        content="different content",
        id=uuid.uuid4(),
    )
    retrieved_chunks = [ChunkWithScore(chunk=different_chunk, score=0.85)]

    result = process_retrieved_chunks(test_question, retrieved_chunks, 100.5)

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
    assert result.expected_chunk.content == ""


def test_process_retrieved_chunks_document_found_chunk_not_found(test_document, test_question):
    """Test processing when correct document is found but specific chunk is not."""
    different_chunk = ChunkFactory.build(
        document=test_document,
        content="different content from same document",
        id=uuid.uuid4(),
    )
    different_chunk.document_id = test_document.id

    retrieved_chunks = [ChunkWithScore(chunk=different_chunk, score=0.85)]

    result = process_retrieved_chunks(test_question, retrieved_chunks, 100.5)

    assert result.correct_chunk_retrieved is False
    assert result.rank_if_found is None

    assert result.correct_document_retrieved is True
    assert result.document_rank_if_found == 1

    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].document_id == str(test_document.id)


def test_batch_process_results(test_document, test_question, enable_factory_create, db_session):
    """Test batch processing of results."""
    questions = [test_question]
    k = 1

    def retrieval_func(query: str, k: int):
        chunk = test_document.chunks[0]
        return [ChunkWithScore(chunk=chunk, score=0.85)]

    results = batch_process_results(questions, retrieval_func, k)

    assert len(results) == 1
    assert isinstance(results[0], EvaluationResult)
    assert results[0].question == test_question["question"]
    assert results[0].retrieval_time_ms > 0
    assert results[0].correct_chunk_retrieved is True

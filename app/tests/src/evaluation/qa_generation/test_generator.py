"""Tests for QA pair generation functionality."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.db.models.document import Chunk, Document
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.generator import QAGenerator, generate_qa_pairs
from src.evaluation.qa_generation.models import QAPair


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = MagicMock(spec=Document)
    doc.id = UUID("123e4567-e89b-12d3-a456-426614174000")
    doc.name = "test_doc"
    doc.source = "test_source"
    doc.dataset = "test_dataset"
    doc.content = "Test document content"
    doc.created_at = datetime.now()
    return doc


@pytest.fixture
def mock_chunk(mock_document):
    """Create a mock chunk."""
    chunk = MagicMock(spec=Chunk)
    chunk.id = UUID("123e4567-e89b-12d3-a456-426614174001")
    chunk.document = mock_document
    chunk.content = "Test chunk content"
    return chunk


@pytest.fixture
def mock_completion_response():
    """Create a mock completion response."""
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(content='{"question": "Test question?", "answer": "Test answer"}')
        )
    ]
    return response


def test_generate_qa_pairs_from_document(mock_document, mock_completion_response):
    """Test generating QA pairs from a document."""
    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 1
        pair = pairs[0]
        assert isinstance(pair, QAPair)
        assert pair.question == "Test question?"
        assert pair.answer == "Test answer"
        assert pair.document_name == mock_document.name
        assert pair.document_source == mock_document.source
        assert pair.document_id == mock_document.id
        assert pair.chunk_id is None
        assert pair.dataset == mock_document.dataset


def test_generate_qa_pairs_from_chunk(mock_chunk, mock_completion_response):
    """Test generating QA pairs from a chunk."""
    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pairs(mock_chunk)

        assert len(pairs) == 1
        pair = pairs[0]
        assert isinstance(pair, QAPair)
        assert pair.question == "Test question?"
        assert pair.answer == "Test answer"
        assert pair.document_name == mock_chunk.document.name
        assert pair.document_source == mock_chunk.document.source
        assert pair.document_id == mock_chunk.document.id
        assert pair.chunk_id == mock_chunk.id
        assert pair.dataset == mock_chunk.document.dataset


def test_generate_qa_pairs_invalid_response(mock_document):
    """Test handling of invalid completion response."""
    # Test with invalid JSON response
    with patch(
        "src.evaluation.qa_generation.generator.completion",
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="invalid json"))]),
    ):
        pairs = generate_qa_pairs(mock_document)
        assert len(pairs) == 0

    # Test with missing required fields
    with patch(
        "src.evaluation.qa_generation.generator.completion",
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"invalid": "response"}'))]
        ),
    ):
        pairs = generate_qa_pairs(mock_document)
        assert len(pairs) == 0


def test_qa_generator_get_chunks_to_process(mock_document, mock_chunk):
    """Test QAGenerator._get_chunks_to_process method."""
    # Setup document with chunks
    mock_document.chunks = [mock_chunk]
    documents = [mock_document]

    # Test document source
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=2)
    generator = QAGenerator(config)
    items = generator._get_chunks_to_process(documents)
    assert len(items) == 1
    assert items[0] == (mock_document, 2)

    # Test chunk source
    config = GenerationConfig(question_source=QuestionSource.CHUNK, questions_per_unit=3)
    generator = QAGenerator(config)
    items = generator._get_chunks_to_process(documents)
    assert len(items) == 1
    assert items[0] == (mock_chunk, 3)


def test_qa_generator_generate_from_documents(mock_document, mock_completion_response):
    """Test QAGenerator.generate_from_documents method."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=1)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = list(generator.generate_from_documents([mock_document]))
        assert len(pairs) == 1
        assert isinstance(pairs[0], QAPair)
        assert pairs[0].question == "Test question?"
        assert pairs[0].answer == "Test answer"

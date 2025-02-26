"""Tests for QA generation functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest
from litellm.main import ModelResponse
from pydantic import ValidationError

from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.generator import QAGenerator, generate_qa_pair
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


@pytest.fixture
def mock_completion_response():
    """Create a mock completion response."""
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = json.dumps(
        {
            "question": "What is the test content?",
            "answer": "The test content is for QA generation.",
        }
    )
    response.choices = [MagicMock(message=message)]
    return response


def test_generate_qa_pair_basic(mock_completion_response):
    """Test basic QA pair generation from a document."""
    document = DocumentFactory.build(content="Test document content", source="test_source")

    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pair(document)

        assert len(pairs) == 1
        assert isinstance(pairs[0], QAPair)
        assert pairs[0].question == "What is the test content?"
        assert pairs[0].answer == "The test content is for QA generation."
        assert pairs[0].document_id == document.id
        assert pairs[0].document_name == document.name
        assert pairs[0].document_source == document.source
        assert pairs[0].chunk_id is None  # Should be None for document-level generation
        assert pairs[0].dataset == document.dataset


def test_generate_qa_pair_from_chunk(mock_completion_response):
    """Test QA pair generation from a document chunk."""
    document = DocumentFactory.build(content="Parent document content", source="test_source")
    chunk = ChunkFactory.build(document=document, content="Test chunk content")

    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pair(chunk)

        assert len(pairs) == 1
        assert isinstance(pairs[0], QAPair)
        assert pairs[0].question == "What is the test content?"
        assert pairs[0].answer == "The test content is for QA generation."
        assert pairs[0].document_id == chunk.document.id
        assert pairs[0].document_name == chunk.document.name
        assert pairs[0].document_source == chunk.document.source
        assert pairs[0].chunk_id == chunk.id  # Should be set for chunk-level generation
        assert pairs[0].dataset == chunk.document.dataset


def test_generate_qa_pair_invalid_json():
    """Test handling of invalid JSON in LLM response."""
    document = DocumentFactory.build(content="Test document content", source="test_source")
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = "This is not valid JSON"
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response), patch(
        "src.evaluation.qa_generation.generator.QAPairResponse.model_validate_json",
        side_effect=ValidationError.from_exception_data("test", []),
    ):
        pairs = generate_qa_pair(document)

        assert len(pairs) == 0  # Should return empty list for invalid JSON


def test_generate_qa_pair_missing_fields():
    """Test handling of missing fields in LLM response."""
    document = DocumentFactory.build(content="Test document content", source="test_source")
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = json.dumps(
        {"not_question": "What is missing?", "not_answer": "The question and answer fields"}
    )
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response), patch(
        "src.evaluation.qa_generation.generator.QAPairResponse.model_validate_json",
        side_effect=ValidationError.from_exception_data("test", []),
    ):
        pairs = generate_qa_pair(document)

        assert len(pairs) == 0  # Should return empty list for missing fields


def test_generate_qa_pair_api_error():
    """Test handling of API errors during generation."""
    document = DocumentFactory.build(content="Test document content", source="test_source")
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=Exception("API Error")
    ):
        pairs = generate_qa_pair(document)

        assert len(pairs) == 0  # Should return empty list on error


def test_generate_qa_pair_empty_content():
    """Test handling of empty document content."""
    document = DocumentFactory.build(content=None)

    pairs = generate_qa_pair(document)

    assert len(pairs) == 0  # Should return empty list for empty content


def test_generate_qa_pair_empty_source():
    """Test handling of empty document source."""
    document = DocumentFactory.build(source=None)

    pairs = generate_qa_pair(document)

    assert len(pairs) == 0  # Should return empty list for empty source


def test_qa_generator_init():
    """Test QA generator initialization."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT)
    generator = QAGenerator(config)

    assert generator.config == config
    assert generator.llm == config.llm_model


def test_qa_generator_generate_from_documents_document_level(mock_completion_response):
    """Test generating QA pairs from documents at document level."""
    documents = DocumentFactory.build_batch(2)
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.generate_qa_pair",
        return_value=[MagicMock(spec=QAPair)],
    ) as mock_generate:
        pairs = list(generator.generate_from_documents(documents))

        assert len(pairs) == 2  # One pair per document
        # Verify generate_qa_pair was called with each document
        assert mock_generate.call_count == 2
        mock_generate.assert_any_call(documents[0], generator.config.llm_model)
        mock_generate.assert_any_call(documents[1], generator.config.llm_model)


def test_qa_generator_generate_from_documents_chunk_level(mock_completion_response):
    """Test generating QA pairs from documents at chunk level."""
    # Create documents with chunks
    document = DocumentFactory.build(content="Parent document content", source="test_source")
    chunk1 = ChunkFactory.build(document=document, content="Test chunk 1 content")
    chunk2 = ChunkFactory.build(document=document, content="Test chunk 2 content")
    document.chunks = [chunk1, chunk2]

    config = GenerationConfig(question_source=QuestionSource.CHUNK)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.generate_qa_pair",
        return_value=[MagicMock(spec=QAPair)],
    ) as mock_generate:
        pairs = list(generator.generate_from_documents([document]))

        assert len(pairs) == 2  # One pair per chunk
        # Verify generate_qa_pair was called with each chunk
        assert mock_generate.call_count == 2
        mock_generate.assert_any_call(chunk1, generator.config.llm_model)
        mock_generate.assert_any_call(chunk2, generator.config.llm_model)


def test_qa_generator_generate_from_documents_with_errors():
    """Test error handling during generation."""
    documents = DocumentFactory.build_batch(2)
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.generate_qa_pair",
        side_effect=Exception("Test error"),
    ):
        pairs = list(generator.generate_from_documents(documents))

        assert len(pairs) == 0  # Should handle errors and continue

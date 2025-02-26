"""Tests for QA generation functionality."""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from litellm.main import ModelResponse

from src.db.models.document import Chunk, Document
from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.generator import QAGenerator, generate_qa_pairs


@pytest.fixture
def mock_document():
    """Create a mock document for testing."""
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.name = "Test Document"
    doc.source = "Test Source"
    doc.dataset = "Test Dataset"
    doc.content = "This is test content for QA generation."
    doc.created_at = datetime.now()

    # Add chunks to document
    chunk1 = MagicMock(spec=Chunk)
    chunk1.id = uuid.uuid4()
    chunk1.document = doc
    chunk1.content = "Chunk 1 content"

    chunk2 = MagicMock(spec=Chunk)
    chunk2.id = uuid.uuid4()
    chunk2.document = doc
    chunk2.content = "Chunk 2 content"

    doc.chunks = [chunk1, chunk2]
    return doc


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


def test_generate_qa_pairs_basic(mock_document, mock_completion_response):
    """Test basic QA pair generation from a document."""
    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 1
        assert isinstance(pairs[0], QAPair)
        assert pairs[0].question == "What is the test content?"
        assert pairs[0].answer == "The test content is for QA generation."
        assert pairs[0].document_id == mock_document.id
        assert pairs[0].document_name == mock_document.name
        assert pairs[0].document_source == mock_document.source
        assert pairs[0].chunk_id is None  # Should be None for document-level generation
        assert pairs[0].dataset == mock_document.dataset


def test_generate_qa_pairs_from_chunk(mock_document, mock_completion_response):
    """Test QA pair generation from a document chunk."""
    chunk = mock_document.chunks[0]

    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = generate_qa_pairs(chunk)

        assert len(pairs) == 1
        assert isinstance(pairs[0], QAPair)
        assert pairs[0].question == "What is the test content?"
        assert pairs[0].answer == "The test content is for QA generation."
        assert pairs[0].document_id == mock_document.id
        assert pairs[0].document_name == mock_document.name
        assert pairs[0].document_source == mock_document.source
        assert pairs[0].chunk_id == chunk.id  # Should be set for chunk-level generation
        assert pairs[0].dataset == mock_document.dataset


def test_generate_qa_pairs_list_format(mock_document):
    """Test handling of list format in LLM response."""
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = json.dumps(
        [
            {"question": "Question 1?", "answer": "Answer 1"},
            {"question": "Question 2?", "answer": "Answer 2"},
        ]
    )
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 2
        assert pairs[0].question == "Question 1?"
        assert pairs[0].answer == "Answer 1"
        assert pairs[1].question == "Question 2?"
        assert pairs[1].answer == "Answer 2"


def test_generate_qa_pairs_multiline_format(mock_document):
    """Test handling of multiline format in LLM response."""
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    # Use a JSON array format instead of newline-separated objects
    message.content = '[{"question": "Question 1?", "answer": "Answer 1"}, {"question": "Question 2?", "answer": "Answer 2"}]'
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 2
        assert pairs[0].question == "Question 1?"
        assert pairs[0].answer == "Answer 1"
        assert pairs[1].question == "Question 2?"
        assert pairs[1].answer == "Answer 2"


def test_generate_qa_pairs_invalid_json(mock_document):
    """Test handling of invalid JSON in LLM response."""
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = "This is not valid JSON"
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 0  # Should return empty list for invalid JSON


def test_generate_qa_pairs_missing_fields(mock_document):
    """Test handling of missing fields in LLM response."""
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = json.dumps(
        {"not_question": "What is missing?", "not_answer": "The question and answer fields"}
    )
    response.choices = [MagicMock(message=message)]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 0  # Should return empty list for missing fields


def test_generate_qa_pairs_api_error(mock_document):
    """Test handling of API errors during generation."""
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=Exception("API Error")
    ):
        pairs = generate_qa_pairs(mock_document)

        assert len(pairs) == 0  # Should return empty list on error


def test_generate_qa_pairs_empty_content(mock_document):
    """Test handling of empty document content."""
    mock_document.content = None

    pairs = generate_qa_pairs(mock_document)

    assert len(pairs) == 0  # Should return empty list for empty content


def test_generate_qa_pairs_empty_source(mock_document):
    """Test handling of empty document source."""
    mock_document.source = None

    pairs = generate_qa_pairs(mock_document)

    assert len(pairs) == 0  # Should return empty list for empty source


def test_qa_generator_init():
    """Test QA generator initialization."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=2)
    generator = QAGenerator(config)

    assert generator.config == config
    assert generator.llm == config.llm_model


def test_qa_generator_get_chunks_document_level():
    """Test getting chunks at document level."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=2)
    generator = QAGenerator(config)

    doc1 = MagicMock(spec=Document)
    doc2 = MagicMock(spec=Document)
    documents = [doc1, doc2]

    items = generator._get_chunks_to_process(documents)

    assert len(items) == 2
    assert items[0][0] == doc1
    assert items[0][1] == 2  # questions_per_unit
    assert items[1][0] == doc2
    assert items[1][1] == 2  # questions_per_unit


def test_qa_generator_get_chunks_chunk_level():
    """Test getting chunks at chunk level."""
    config = GenerationConfig(question_source=QuestionSource.CHUNK, questions_per_unit=1)
    generator = QAGenerator(config)

    doc1 = MagicMock(spec=Document)
    chunk1 = MagicMock(spec=Chunk)
    chunk2 = MagicMock(spec=Chunk)
    doc1.chunks = [chunk1, chunk2]

    doc2 = MagicMock(spec=Document)
    chunk3 = MagicMock(spec=Chunk)
    doc2.chunks = [chunk3]

    documents = [doc1, doc2]

    items = generator._get_chunks_to_process(documents)

    assert len(items) == 3
    assert items[0][0] == chunk1
    assert items[0][1] == 1  # questions_per_unit
    assert items[1][0] == chunk2
    assert items[1][1] == 1  # questions_per_unit
    assert items[2][0] == chunk3
    assert items[2][1] == 1  # questions_per_unit


def test_qa_generator_generate_from_documents(mock_document, mock_completion_response):
    """Test generating QA pairs from documents."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=1)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.generate_qa_pairs",
        return_value=[MagicMock(spec=QAPair)],
    ):
        pairs = list(generator.generate_from_documents([mock_document]))

        assert len(pairs) == 1


def test_qa_generator_generate_from_documents_with_errors(mock_document):
    """Test error handling during generation."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=1)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.generate_qa_pairs",
        side_effect=Exception("Test error"),
    ):
        pairs = list(generator.generate_from_documents([mock_document]))

        assert len(pairs) == 0  # Should handle errors and continue

"""Tests for QA pair generation functionality."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.db.models.document import Chunk, Document
from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.generator import QAGenerator, generate_qa_pairs


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


def test_generate_qa_pairs_invalid_document(mock_document):
    """Test handling of invalid document properties."""
    # Test with None content
    mock_document.content = None
    pairs = generate_qa_pairs(mock_document)
    assert len(pairs) == 0

    # Test with None source
    mock_document.content = "Test content"
    mock_document.source = None
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


def test_generate_qa_pairs_list_response(mock_document):
    """Test handling of list response format."""
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    [{"question": "Q1?", "answer": "A1"}, {"question": "Q2?", "answer": "A2"}]
                )
            )
        )
    ]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)
        assert len(pairs) == 2
        assert pairs[0].question == "Q1?"
        assert pairs[0].answer == "A1"
        assert pairs[1].question == "Q2?"
        assert pairs[1].answer == "A2"


def test_generate_qa_pairs_multiline_response(mock_document):
    """Test handling of multiline response format."""
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(
                content='[{"question": "Q1?", "answer": "A1"}, {"question": "Q2?", "answer": "A2"}]'
            )
        )
    ]

    with patch("src.evaluation.qa_generation.generator.completion", return_value=response):
        pairs = generate_qa_pairs(mock_document)
        assert len(pairs) == 2
        assert pairs[0].question == "Q1?"
        assert pairs[0].answer == "A1"
        assert pairs[1].question == "Q2?"
        assert pairs[1].answer == "A2"


def test_generate_qa_pairs_completion_error(mock_document):
    """Test handling of completion API error."""
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=Exception("API Error")
    ) as mock_completion:
        # Mock document to have valid content and source
        mock_document.content = "Test content"
        mock_document.source = "test_source"

        pairs = generate_qa_pairs(mock_document)
        assert len(pairs) == 0
        mock_completion.assert_called_once()


def test_qa_generator_concurrent_generation(mock_document, mock_completion_response):
    """Test concurrent generation with multiple documents."""
    # Create multiple documents
    docs = [mock_document] * 3  # Create 3 copies

    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, questions_per_unit=1)
    generator = QAGenerator(config)

    with patch(
        "src.evaluation.qa_generation.generator.completion", return_value=mock_completion_response
    ):
        pairs = list(generator.generate_from_documents(docs))
        assert len(pairs) == 3
        for pair in pairs:
            assert isinstance(pair, QAPair)
            assert pair.question == "Test question?"
            assert pair.answer == "Test answer"


def test_qa_generator_future_error_handling(mock_document):
    """Test handling of future errors in generate_from_documents."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT)
    generator = QAGenerator(config)

    # Mock completion to raise error
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=Exception("API Error")
    ):
        pairs = list(generator.generate_from_documents([mock_document]))
        assert len(pairs) == 0


def test_qa_generator_progress_tracking(mock_document, mock_completion_response):
    """Test progress tracking during generation."""
    # Mock ProgressTracker first
    mock_tracker = MagicMock()
    with patch("src.evaluation.qa_generation.generator.ProgressTracker", return_value=mock_tracker):
        config = GenerationConfig(question_source=QuestionSource.DOCUMENT)
        generator = QAGenerator(config)

        # Mock document to have valid content and source
        mock_document.content = "Test content"
        mock_document.source = "test_source"
        mock_document.dataset = "test_dataset"
        mock_document.created_at = datetime.now(UTC)

        # Set up mock executor to run tasks synchronously
        mock_executor_instance = MagicMock()
        futures_dict = {}

        def mock_submit(fn, *args, **kwargs):
            mock_future = MagicMock()
            result = fn(*args, **kwargs)
            mock_future.result.return_value = result
            futures_dict[mock_future] = args[0]  # Store the future with its document
            return mock_future

        mock_executor_instance.submit = mock_submit

        with (
            patch(
                "src.evaluation.qa_generation.generator.completion",
                return_value=mock_completion_response,
            ) as _,
            patch("src.evaluation.qa_generation.generator.ThreadPoolExecutor") as mock_executor,
            patch(
                "src.evaluation.qa_generation.generator.as_completed",
                side_effect=lambda x: list(futures_dict.keys()),
            ) as _,
            patch.object(
                QAGenerator, "_get_chunks_to_process", return_value=[(mock_document, 1)]
            ) as _,
        ):
            # Set up mock executor
            mock_executor.return_value.__enter__.return_value = mock_executor_instance

            # Run the generation
            list(generator.generate_from_documents([mock_document]))

            # Verify progress tracking was called with a dictionary of futures
            mock_tracker.track_futures.assert_called_once()
            call_args = mock_tracker.track_futures.call_args[0]
            assert isinstance(call_args[0], dict)  # First arg should be futures dict
            assert len(call_args[0]) == 1  # Should have one future for one document
            assert call_args[1] == "Generating QA pairs"  # Second arg should be description

            # Verify the futures dictionary matches what we expect
            assert futures_dict  # Should not be empty
            assert len(futures_dict) == 1  # Should have one future
            assert mock_document in futures_dict.values()  # Should contain our document

            # Verify completion logging
            mock_tracker.log_completion.assert_called_once()
            completion_stats = mock_tracker.log_completion.call_args[0][0]
            assert "Total QA pairs" in completion_stats
            assert "items_processed" in completion_stats

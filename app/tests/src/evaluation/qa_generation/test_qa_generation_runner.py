"""Tests for QA generation runner."""

import csv
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.runner import run_generation, save_qa_pairs
from tests.src.db.models.factories import DocumentFactory


@pytest.fixture
def qa_pairs():
    """Create QA pairs for testing."""
    qa_pair1 = QAPair(
        id=uuid.uuid4(),
        question="Question 1?",
        answer="Answer 1",
        document_name="Document 1",
        document_source="Source 1",
        document_id=uuid.uuid4(),
        chunk_id=None,
        content_hash="hash1",
        dataset="Dataset 1",
        llm_model="gpt-4o-mini",
        created_at=datetime.now(),
    )

    qa_pair2 = QAPair(
        id=uuid.uuid4(),
        question="Question 2?",
        answer="Answer 2",
        document_name="Document 2",
        document_source="Source 2",
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        content_hash="hash2",
        dataset="Dataset 2",
        llm_model="gpt-4o-mini",
        created_at=datetime.now(),
    )

    return [qa_pair1, qa_pair2]


def test_save_qa_pairs(qa_pairs, tmp_path):
    """Test save_qa_pairs function with real file operations."""
    # Create a temporary directory for output
    output_dir = tmp_path / "qa_pairs"

    # Call the function with real QA pairs
    result_path = save_qa_pairs(output_dir, qa_pairs)

    # Verify the file was created
    assert result_path.exists()
    assert result_path == output_dir / "qa_pairs.csv"

    # Read the CSV file and verify its contents
    with open(result_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Verify we have the correct number of rows
        assert len(rows) == len(qa_pairs)

        # Verify the content of each row
        for i, row in enumerate(rows):
            assert row["question"] == qa_pairs[i].question
            assert row["answer"] == qa_pairs[i].answer
            assert row["document_name"] == qa_pairs[i].document_name
            assert row["dataset"] == qa_pairs[i].dataset


def test_run_generation_basic(qa_pairs, tmp_path):
    """Test basic run_generation functionality with minimal mocking."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, llm_model="gpt-4o-mini")
    output_dir = tmp_path / "qa_output"

    # Create test documents using DocumentFactory
    documents = DocumentFactory.build_batch(2)

    with (
        # Only mock the generate_from_documents method, not the entire QAGenerator class
        patch("src.evaluation.qa_generation.generator.generate_qa_pair") as mock_generate_qa_pair,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
    ):
        # Set up the mock to return our test QA pairs
        mock_generate_qa_pair.return_value = [qa_pairs[0]]  # Return one QA pair per document

        # Mock db_session to return our test documents
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Run the function
        result = run_generation(config, output_dir)

        # Verify results
        assert result.exists()
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"

        # Verify the generate_qa_pair function was called for each document
        assert mock_generate_qa_pair.call_count == len(documents)

        # Verify the CSV file exists and contains data
        with open(result, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) > 0


def test_run_generation_with_dataset_filter(qa_pairs, tmp_path):
    """Test run_generation with dataset filter."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, llm_model="gpt-4o-mini")
    output_dir = tmp_path / "qa_output"
    dataset_filter = ["Dataset 1"]

    # Create test documents with different datasets
    documents = [
        DocumentFactory.build(dataset="Dataset 1"),
        DocumentFactory.build(dataset="Dataset 2"),
    ]

    with (
        patch("src.evaluation.qa_generation.generator.generate_qa_pair") as mock_generate_qa_pair,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
    ):
        # Set up the mock to return our test QA pairs
        mock_generate_qa_pair.return_value = [qa_pairs[0]]

        # Mock db_session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Run the function
        result = run_generation(config, output_dir, dataset_filter=dataset_filter)

        # Verify results
        assert result.exists()
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"

        # Verify the filter was applied
        mock_query.filter.assert_called_once()


def test_run_generation_with_sampling(qa_pairs, tmp_path):
    """Test run_generation with sampling using real sampling function."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, llm_model="gpt-4o-mini")
    output_dir = tmp_path / "qa_output"
    sample_fraction = 0.5
    random_seed = 42

    # Create test documents
    documents = DocumentFactory.build_batch(4, dataset="Dataset 1")

    with (
        patch("src.evaluation.qa_generation.generator.generate_qa_pair") as mock_generate_qa_pair,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
        # We still need to mock the sampling function to make the test deterministic
        patch("src.evaluation.qa_generation.runner.get_stratified_sample") as mock_sample,
    ):
        # Set up the mock to return our test QA pairs
        mock_generate_qa_pair.return_value = [qa_pairs[0]]

        # Mock db_session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Mock the sampling function to return a subset
        mock_sample.return_value = documents[:2]

        # Run the function
        result = run_generation(
            config, output_dir, sample_fraction=sample_fraction, random_seed=random_seed
        )

        # Verify results
        assert result.exists()
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"

        # Verify sampling was called correctly
        mock_sample.assert_called_once()
        call_args = mock_sample.call_args
        assert call_args[0][0] == documents  # First positional arg should be documents
        assert call_args[1]["sample_fraction"] == sample_fraction
        assert call_args[1]["random_seed"] == random_seed


def test_run_generation_no_documents(tmp_path):
    """Test run_generation with no documents found."""
    config = GenerationConfig(question_source=QuestionSource.DOCUMENT, llm_model="gpt-4o-mini")
    output_dir = tmp_path / "qa_output"

    with (patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,):
        # Mock db_session to return empty list
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = []  # No documents found
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Run the function and expect ValueError
        with pytest.raises(ValueError, match="No documents found matching filter criteria"):
            run_generation(config, output_dir)

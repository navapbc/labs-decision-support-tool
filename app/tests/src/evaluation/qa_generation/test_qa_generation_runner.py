"""Tests for QA generation runner."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.document import Document
from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource
from src.evaluation.qa_generation.runner import QAPairStorage, run_generation


@pytest.fixture
def mock_documents():
    """Create mock documents for testing."""
    doc1 = MagicMock(spec=Document)
    doc1.id = uuid.uuid4()
    doc1.name = "Document 1"
    doc1.source = "Source 1"
    doc1.dataset = "Dataset 1"
    doc1.content = "Content 1"
    doc1.created_at = datetime.now()

    doc2 = MagicMock(spec=Document)
    doc2.id = uuid.uuid4()
    doc2.name = "Document 2"
    doc2.source = "Source 2"
    doc2.dataset = "Dataset 2"
    doc2.content = "Content 2"
    doc2.created_at = datetime.now()

    return [doc1, doc2]


@pytest.fixture
def mock_qa_pairs():
    """Create mock QA pairs."""
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


def test_qa_pair_storage_init(tmp_path):
    """Test QAPairStorage initialization."""
    output_dir = tmp_path / "qa_pairs"

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        storage = QAPairStorage(output_dir)

        assert storage.output_dir == output_dir
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_qa_pair_storage_save_qa_pairs(mock_qa_pairs, tmp_path):
    """Test QAPairStorage.save_qa_pairs method."""
    output_dir = tmp_path / "qa_pairs"
    storage = QAPairStorage(output_dir)

    with patch("builtins.open", MagicMock()), patch("csv.DictWriter") as mock_writer:
        mock_writer_instance = MagicMock()
        mock_writer.return_value = mock_writer_instance

        result = storage.save_qa_pairs(mock_qa_pairs)

        assert result == output_dir / "qa_pairs.csv"
        mock_writer_instance.writeheader.assert_called_once()
        assert mock_writer_instance.writerow.call_count == len(mock_qa_pairs)


def test_run_generation_basic(mock_documents, mock_qa_pairs, tmp_path):
    """Test basic run_generation functionality."""
    config = GenerationConfig(
        question_source=QuestionSource.DOCUMENT, questions_per_unit=1, llm_model="gpt-4o-mini"
    )
    output_dir = tmp_path / "qa_output"

    with (
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_cls,
        patch("src.evaluation.qa_generation.runner.QAPairStorage") as mock_storage_cls,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
    ):
        # Set up mocks
        mock_generator_instance = MagicMock()
        mock_generator_instance.generate_from_documents.return_value = mock_qa_pairs
        mock_generator_cls.return_value = mock_generator_instance

        mock_storage_instance = MagicMock()
        mock_storage_instance.save_qa_pairs.return_value = output_dir / "qa_pairs" / "qa_pairs.csv"
        mock_storage_cls.return_value = mock_storage_instance

        # Mock db_session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = mock_documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Run the function
        result = run_generation(config, output_dir)

        # Verify results
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"
        mock_generator_cls.assert_called_once_with(config)
        mock_generator_instance.generate_from_documents.assert_called_once_with(mock_documents)
        mock_storage_instance.save_qa_pairs.assert_called_once_with(qa_pairs=mock_qa_pairs)


def test_run_generation_with_dataset_filter(mock_documents, mock_qa_pairs, tmp_path):
    """Test run_generation with dataset filter."""
    config = GenerationConfig(
        question_source=QuestionSource.DOCUMENT, questions_per_unit=1, llm_model="gpt-4o-mini"
    )
    output_dir = tmp_path / "qa_output"
    dataset_filter = ["Dataset 1"]

    with (
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_cls,
        patch("src.evaluation.qa_generation.runner.QAPairStorage") as mock_storage_cls,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
    ):
        # Set up mocks
        mock_generator_instance = MagicMock()
        mock_generator_instance.generate_from_documents.return_value = mock_qa_pairs
        mock_generator_cls.return_value = mock_generator_instance

        mock_storage_instance = MagicMock()
        mock_storage_instance.save_qa_pairs.return_value = output_dir / "qa_pairs" / "qa_pairs.csv"
        mock_storage_cls.return_value = mock_storage_instance

        # Mock db_session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = mock_documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        # Run the function
        result = run_generation(config, output_dir, dataset_filter=dataset_filter)

        # Verify results
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"
        mock_query.filter.assert_called_once()  # Should filter by dataset


def test_run_generation_with_sampling(mock_documents, mock_qa_pairs, tmp_path):
    """Test run_generation with sampling."""
    config = GenerationConfig(
        question_source=QuestionSource.DOCUMENT, questions_per_unit=1, llm_model="gpt-4o-mini"
    )
    output_dir = tmp_path / "qa_output"
    sample_fraction = 0.5
    random_seed = 42

    with (
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_cls,
        patch("src.evaluation.qa_generation.runner.QAPairStorage") as mock_storage_cls,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
        patch("src.evaluation.qa_generation.runner.get_stratified_sample") as mock_sample,
    ):
        # Set up mocks
        mock_generator_instance = MagicMock()
        mock_generator_instance.generate_from_documents.return_value = mock_qa_pairs
        mock_generator_cls.return_value = mock_generator_instance

        mock_storage_instance = MagicMock()
        mock_storage_instance.save_qa_pairs.return_value = output_dir / "qa_pairs" / "qa_pairs.csv"
        mock_storage_cls.return_value = mock_storage_instance

        # Mock db_session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.all.return_value = mock_documents
        mock_session.query.return_value = mock_query

        # Set up context manager for db_session
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_app_config.db_session.return_value = mock_session_cm

        mock_sample.return_value = mock_documents[:1]  # Return a subset

        # Run the function
        result = run_generation(
            config, output_dir, sample_fraction=sample_fraction, random_seed=random_seed
        )

        # Verify results
        assert result == output_dir / "qa_pairs" / "qa_pairs.csv"

        # Use assert_called_once() instead of assert_called_once_with() to avoid lambda comparison issues
        assert mock_sample.call_count == 1
        call_args = mock_sample.call_args
        assert call_args[0][0] == mock_documents  # First positional arg should be documents
        assert call_args[1]["sample_fraction"] == sample_fraction
        assert call_args[1]["random_seed"] == random_seed
        # Don't check the key_func as it's a lambda and will have different object IDs

        mock_generator_instance.generate_from_documents.assert_called_once_with(mock_documents[:1])


def test_run_generation_no_documents(tmp_path):
    """Test run_generation with no documents found."""
    config = GenerationConfig(
        question_source=QuestionSource.DOCUMENT, questions_per_unit=1, llm_model="gpt-4o-mini"
    )
    output_dir = tmp_path / "qa_output"

    with (
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_cls,
        patch("src.evaluation.qa_generation.runner.QAPairStorage") as mock_storage_cls,
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
    ):
        # Set up mocks
        mock_generator_instance = MagicMock()
        mock_generator_cls.return_value = mock_generator_instance

        # Mock db_session
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

        # QAGenerator is created but generate_from_documents should not be called
        mock_generator_cls.assert_called_once_with(config)
        mock_generator_instance.generate_from_documents.assert_not_called()

        # Storage should not be called
        mock_storage_cls.assert_not_called()

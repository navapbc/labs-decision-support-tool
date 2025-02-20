"""Tests for QA generation runner functionality."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.db.models.document import Chunk, Document
from src.evaluation.qa_generation.config import GenerationConfig
from src.evaluation.qa_generation.runner import run_generation


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock(spec=Session)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=None)
    return session


@pytest.fixture
def mock_documents():
    """Create a list of mock documents."""
    docs = []
    for i in range(3):
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.name = f"test_doc_{i}"
        doc.source = "test_source"
        doc.dataset = f"test_dataset_{i % 2}"  # Create docs from 2 datasets
        doc.content = f"Test document content {i}"
        doc.created_at = datetime.now(UTC)

        # Add chunks to document
        chunks = []
        for j in range(2):
            chunk = MagicMock(spec=Chunk)
            chunk.id = uuid.uuid4()
            chunk.content = f"Test chunk content {j}"
            chunk.document = doc
            chunks.append(chunk)
        doc.chunks = chunks
        docs.append(doc)
    return docs


@pytest.fixture
def mock_qa_pairs():
    """Create mock QA pairs."""
    from src.evaluation.data_models import QAPair, QAPairVersion

    version = QAPairVersion(
        version_id="test_version", timestamp=datetime.now(UTC).isoformat(), llm_model="test-model"
    )
    return [
        QAPair(
            id=str(uuid.uuid4()),
            question=f"Test question {i}?",
            answer=f"Test answer {i}",
            document_name=f"test_doc_{i}",
            document_source="test_source",
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            content_hash=f"hash_{i}",
            dataset="test_dataset",
            created_at=datetime.now(UTC).isoformat(),
            version=version,
        )
        for i in range(2)
    ]


def test_run_generation_basic(tmp_path, mock_session, mock_documents, mock_qa_pairs):
    """Test basic run_generation functionality."""
    config = GenerationConfig(llm_model="test-model")
    output_dir = tmp_path / "output"

    # Mock DB session query
    mock_session.query.return_value.all.return_value = mock_documents

    with (
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_class,
        patch("src.evaluation.qa_generation.runner.QAPairStorage") as MockQAPairStorage,
    ):
        # Setup mocks
        mock_app_config.db_session.return_value = mock_session
        mock_generator = mock_generator_class.return_value
        mock_generator.generate_from_documents.return_value = mock_qa_pairs

        mock_storage = MockQAPairStorage.return_value
        expected_path = output_dir / "qa_pairs/test_version/qa_pairs.csv"
        mock_storage.save_qa_pairs.return_value = expected_path

        # Run generation
        result_path = run_generation(config=config, output_dir=output_dir)

        # Verify results
        assert result_path == expected_path
        mock_generator.generate_from_documents.assert_called_once_with(mock_documents)
        mock_storage.save_qa_pairs.assert_called_once()
        mock_generator.progress.log_completion.assert_called_once()


def test_run_generation_with_dataset_filter(tmp_path, mock_session, mock_documents):
    """Test run_generation with dataset filtering."""
    config = GenerationConfig(llm_model="test-model")

    # Mock DB session query with filter
    mock_query = mock_session.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.all.return_value = [d for d in mock_documents if d.dataset == "test_dataset_0"]

    with (
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_class,
        patch("src.evaluation.qa_generation.runner.QAPairStorage"),
    ):
        mock_app_config.db_session.return_value = mock_session
        mock_generator = mock_generator_class.return_value

        # Run generation with dataset filter
        run_generation(config=config, output_dir=tmp_path, dataset_filter=["test_dataset_0"])

        # Verify filtered documents were used
        called_docs = mock_generator.generate_from_documents.call_args[0][0]
        assert all(d.dataset == "test_dataset_0" for d in called_docs)


def test_run_generation_with_sampling(tmp_path, mock_session, mock_documents):
    """Test run_generation with document sampling."""
    config = GenerationConfig(llm_model="test-model")

    # Mock DB session query
    mock_session.query.return_value.all.return_value = mock_documents

    with (
        patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config,
        patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_class,
        patch("src.evaluation.qa_generation.runner.QAPairStorage"),
        patch("src.evaluation.qa_generation.runner.get_stratified_sample") as mock_sample,
    ):
        mock_app_config.db_session.return_value = mock_session
        mock_generator = mock_generator_class.return_value
        sampled_docs = mock_documents[:1]  # Subset of documents
        mock_sample.return_value = sampled_docs

        # Run generation with sampling
        run_generation(config=config, output_dir=tmp_path, sample_fraction=0.5, random_seed=42)

        # Verify sampling was called with correct parameters
        mock_sample.assert_called_once()
        assert mock_sample.call_args[1]["sample_fraction"] == 0.5
        assert mock_sample.call_args[1]["random_seed"] == 42

        # Verify generator was called with sampled documents
        mock_generator.generate_from_documents.assert_called_once_with(sampled_docs)


def test_run_generation_no_llm_model(tmp_path):
    """Test run_generation fails when no LLM model specified."""
    config = GenerationConfig()  # No llm_model specified

    with patch("src.evaluation.qa_generation.runner.QAGenerator") as mock_generator_class:
        mock_generator = mock_generator_class.return_value
        mock_generator.generate_from_documents.side_effect = ValueError(
            "No LLM model specified for QA generation"
        )

        with pytest.raises(ValueError, match="No LLM model specified for QA generation"):
            run_generation(config=config, output_dir=tmp_path)


def test_run_generation_no_documents(tmp_path, mock_session):
    """Test run_generation fails when no documents found."""
    config = GenerationConfig(llm_model="test-model")

    # Mock empty DB query result
    mock_session.query.return_value.all.return_value = []

    with patch("src.evaluation.qa_generation.runner.app_config") as mock_app_config:
        # Setup mock database session
        mock_app_config.db_session.return_value = mock_session

        with pytest.raises(ValueError, match="No documents found matching filter criteria"):
            run_generation(config=config, output_dir=tmp_path)

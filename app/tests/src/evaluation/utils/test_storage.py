"""Tests for QA pairs storage utilities."""

import json
import uuid
from datetime import datetime

import pytest

from src.evaluation.data_models import QAPair, QAPairVersion
from src.evaluation.utils.storage import QAPairStorage


@pytest.fixture
def storage_dir(tmp_path):
    """Create a temporary directory for storage tests."""
    return tmp_path / "qa_pairs"


@pytest.fixture
def storage(storage_dir):
    """Create a QAPairStorage instance for testing."""
    return QAPairStorage(storage_dir)


@pytest.fixture
def sample_qa_pairs():
    """Create sample QA pairs for testing."""
    version = QAPairVersion(
        version_id="test_v1",
        llm_model="test-model",
        timestamp=datetime.utcnow(),
    )

    return [
        QAPair(
            id=uuid.uuid4(),
            question="Test question 1?",
            answer="Test answer 1",
            document_name="doc1.txt",
            document_source="test_dataset",
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            content_hash="hash1",
            dataset="test_dataset",
            version=version,
        ),
        QAPair(
            id=uuid.uuid4(),
            question="Test question 2?",
            answer="Test answer 2",
            document_name="doc2.txt",
            document_source="test_dataset",
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            content_hash="hash2",
            dataset="test_dataset",
            version=version,
        ),
    ]


def test_save_qa_pairs(storage, sample_qa_pairs):
    """Test saving QA pairs with version information."""
    version_id = "test_v1"
    git_commit = "abc123"

    csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id, git_commit)

    # Check that files were created
    assert csv_path.exists()
    assert (csv_path.parent / "metadata.json").exists()

    # Check metadata content
    with open(csv_path.parent / "metadata.json") as f:
        metadata = json.load(f)
        assert metadata["version_id"] == version_id
        assert metadata["git_commit"] == git_commit
        assert metadata["llm_model"] == "test-model"
        assert metadata["total_pairs"] == 2
        assert metadata["datasets"] == ["test_dataset"]


def test_get_latest_version_empty(storage):
    """Test getting latest version with no QA pairs."""
    with pytest.raises(ValueError, match="No QA pairs found"):
        storage.get_latest_version()


def test_get_latest_version(storage, sample_qa_pairs):
    """Test getting latest version with multiple versions."""
    # Save two versions
    storage.save_qa_pairs(sample_qa_pairs, "v1", "commit1")
    storage.save_qa_pairs(sample_qa_pairs, "v2", "commit2")

    latest = storage.get_latest_version()
    assert latest == "v2"

    # Check that latest symlink points to v2
    latest_link = storage.base_path / "latest"
    assert latest_link.exists()
    assert latest_link.resolve().name == "v2"


def test_get_version_path(storage, sample_qa_pairs):
    """Test getting path for specific version."""
    version_id = "test_v1"
    storage.save_qa_pairs(sample_qa_pairs, version_id, "commit1")

    path = storage.get_version_path(version_id)
    assert path.exists()
    assert path.is_dir()
    assert path.name == version_id

    # Test non-existent version
    with pytest.raises(ValueError, match="Version bad_version not found"):
        storage.get_version_path("bad_version")


def test_get_version_metadata(storage, sample_qa_pairs):
    """Test getting metadata for specific version."""
    version_id = "test_v1"
    git_commit = "commit1"
    storage.save_qa_pairs(sample_qa_pairs, version_id, git_commit)

    metadata = storage.get_version_metadata(version_id)
    assert metadata["version_id"] == version_id
    assert metadata["git_commit"] == git_commit
    assert metadata["llm_model"] == "test-model"

    # Test non-existent version
    with pytest.raises(ValueError, match="Version bad_version not found"):
        storage.get_version_metadata("bad_version")

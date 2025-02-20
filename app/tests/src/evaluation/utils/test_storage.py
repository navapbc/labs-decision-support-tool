"""Tests for QA pair storage utilities."""

import csv
import json
import os
from datetime import UTC, datetime

import pytest

from src.evaluation.data_models import QAPair, QAPairVersion
from src.evaluation.utils.storage import QAPairStorage


@pytest.fixture
def temp_storage_dir(tmp_path):
    """Create a temporary directory for storage tests."""
    return tmp_path / "qa_pairs"


@pytest.fixture
def storage(temp_storage_dir):
    """Create a QAPairStorage instance with temp directory."""
    return QAPairStorage(temp_storage_dir)


@pytest.fixture
def sample_qa_pairs():
    """Create sample QA pairs for testing."""
    version = QAPairVersion(
        version_id="20240220_test", timestamp=datetime.now(UTC).isoformat(), llm_model="test-model"
    )

    return [
        QAPair(
            id="test1",
            question="What is X?",
            answer="X is a test",
            document_name="doc1.txt",
            document_source="test_dataset",
            document_id="doc1",
            chunk_id="chunk1",
            content_hash="hash1",
            dataset="test_dataset",
            created_at=datetime.now(UTC).isoformat(),
            version=version,
        ),
        QAPair(
            id="test2",
            question="What is Y?",
            answer="Y is another test",
            document_name="doc2.txt",
            document_source="test_dataset",
            document_id="doc2",
            chunk_id="chunk2",
            content_hash="hash2",
            dataset="test_dataset",
            created_at=datetime.now(UTC).isoformat(),
            version=version,
        ),
    ]


def test_storage_init(temp_storage_dir):
    """Test storage initialization creates directory."""
    # Before initialization, directory should not exist
    assert not temp_storage_dir.exists()

    # Creating storage should create the directory
    storage = QAPairStorage(temp_storage_dir)
    assert storage.base_path.exists()
    assert storage.base_path.is_dir()


def test_save_qa_pairs(storage, sample_qa_pairs):
    """Test saving QA pairs creates expected files and structure."""
    version_id = "test_version"
    git_commit = "abc123"

    # Save QA pairs
    csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id, git_commit)

    # Check CSV file exists and has correct structure
    assert csv_path.exists()
    assert csv_path.name == "qa_pairs.csv"

    # Check metadata file exists and has correct content
    metadata_path = csv_path.parent / "metadata.json"
    assert metadata_path.exists()

    with open(metadata_path) as f:
        metadata = json.load(f)
        assert metadata["version_id"] == version_id
        assert metadata["git_commit"] == git_commit
        assert metadata["total_pairs"] == len(sample_qa_pairs)
        assert metadata["llm_model"] == "test-model"
        assert "test_dataset" in metadata["datasets"]


def test_save_qa_pairs_empty_list(storage):
    """Test saving empty QA pairs list."""
    version_id = "test_version"

    # Save empty QA pairs list
    csv_path = storage.save_qa_pairs([], version_id)

    # Check files still created
    assert csv_path.exists()
    metadata_path = csv_path.parent / "metadata.json"
    assert metadata_path.exists()

    # Check metadata reflects empty list
    with open(metadata_path) as f:
        metadata = json.load(f)
        assert metadata["total_pairs"] == 0
        assert metadata["llm_model"] is None
        assert metadata["datasets"] == []


def test_get_latest_version_empty(storage):
    """Test getting latest version with no data raises error."""
    with pytest.raises(ValueError, match="No QA pairs found"):
        storage.get_latest_version()


def test_get_latest_version(storage, sample_qa_pairs):
    """Test getting latest version returns most recent."""
    # Create multiple versions
    version1 = "20240219_test"
    version2 = "20240220_test"

    storage.save_qa_pairs(sample_qa_pairs, version1)
    storage.save_qa_pairs(sample_qa_pairs, version2)

    latest = storage.get_latest_version()
    assert latest == version2


def test_get_latest_version_symlink(storage, sample_qa_pairs):
    """Test latest version symlink is created and updated."""
    version1 = "20240219_test"
    version2 = "20240220_test"

    # Save first version and check symlink
    storage.save_qa_pairs(sample_qa_pairs, version1)
    latest_link = storage.base_path / "latest"
    assert latest_link.is_symlink()
    assert latest_link.resolve().name == version1

    # Save second version and check symlink updates
    storage.save_qa_pairs(sample_qa_pairs, version2)
    assert latest_link.is_symlink()
    assert latest_link.resolve().name == version2


def test_get_version_path(storage, sample_qa_pairs):
    """Test getting path for specific version."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    path = storage.get_version_path(version_id)
    assert path.exists()
    assert path.is_dir()
    assert path.name == version_id


def test_get_version_path_not_found(storage):
    """Test getting path for non-existent version raises error."""
    with pytest.raises(ValueError, match="Version .* not found"):
        storage.get_version_path("nonexistent")


def test_get_version_metadata(storage, sample_qa_pairs):
    """Test getting metadata for specific version."""
    version_id = "test_version"
    git_commit = "abc123"

    storage.save_qa_pairs(sample_qa_pairs, version_id, git_commit)

    metadata = storage.get_version_metadata(version_id)
    assert metadata["version_id"] == version_id
    assert metadata["git_commit"] == git_commit
    assert metadata["total_pairs"] == len(sample_qa_pairs)


def test_get_version_metadata_not_found(storage):
    """Test getting metadata for non-existent version raises error."""
    with pytest.raises(ValueError, match="Version .* not found"):
        storage.get_version_metadata("nonexistent")


def test_get_version_metadata_missing_file(storage, sample_qa_pairs):
    """Test getting metadata when metadata file is missing."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Delete metadata file
    metadata_path = storage.get_version_path(version_id) / "metadata.json"
    metadata_path.unlink()

    with pytest.raises(ValueError, match="Metadata not found"):
        storage.get_version_metadata(version_id)


def test_save_qa_pairs_verify_csv_content(storage, sample_qa_pairs):
    """Test CSV file content is correct."""
    version_id = "test_version"
    csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Read CSV and verify content
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        assert len(rows) == len(sample_qa_pairs)
        for row, pair in zip(rows, sample_qa_pairs, strict=True):
            assert row["id"] == pair.id
            assert row["question"] == pair.question
            assert row["answer"] == pair.answer
            assert row["document_name"] == pair.document_name
            assert row["source"] == pair.document_source
            assert row["version_id"] == pair.version.version_id
            assert row["version_llm_model"] == pair.version.llm_model


def test_save_qa_pairs_broken_symlink(storage, sample_qa_pairs):
    """Test handling of broken symlink during save."""
    version_id = "test_version"
    latest_link = storage.base_path / "latest"

    # Create a broken symlink
    nonexistent = storage.base_path / "nonexistent"
    latest_link.symlink_to(nonexistent, target_is_directory=True)

    # Save should succeed and fix symlink
    csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id)
    assert latest_link.exists()
    assert latest_link.is_symlink()
    assert latest_link.resolve() == csv_path.parent


def test_get_latest_version_multiple_versions(storage, sample_qa_pairs):
    """Test getting latest version with multiple versions in non-sequential order."""
    # Create versions in non-sequential order
    versions = ["20240219_test", "20240221_test", "20240220_test"]
    for version in versions:
        storage.save_qa_pairs(sample_qa_pairs, version)

    latest = storage.get_latest_version()
    assert latest == "20240221_test"  # Should get chronologically latest


def test_get_latest_version_broken_symlink(storage, sample_qa_pairs):
    """Test getting latest version handles broken symlink."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Create broken symlink
    latest_link = storage.base_path / "latest"
    latest_link.unlink()
    nonexistent = storage.base_path / "nonexistent"
    latest_link.symlink_to(nonexistent, target_is_directory=True)

    # Should still work by finding latest version
    latest = storage.get_latest_version()
    assert latest == version_id
    # Should fix symlink
    assert latest_link.resolve() == storage.base_path / version_id


@pytest.mark.skipif(os.name == "nt", reason="Permission tests not supported on Windows")
def test_save_qa_pairs_permission_error(storage, sample_qa_pairs):
    """Test handling of permission error during save."""
    version_id = "test_version"

    # Store original permissions
    original_mode = storage.base_path.stat().st_mode

    # Make base directory read-only
    os.chmod(storage.base_path, 0o444)
    try:
        with pytest.raises(PermissionError):
            storage.save_qa_pairs(sample_qa_pairs, version_id)
    finally:
        # Restore original permissions for cleanup
        os.chmod(storage.base_path, original_mode)


def test_save_qa_pairs_existing_version(storage, sample_qa_pairs):
    """Test saving to an existing version directory."""
    version_id = "test_version"

    # Save first time
    first_path = storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Save again to same version - should work and overwrite
    second_path = storage.save_qa_pairs(sample_qa_pairs, version_id)
    assert first_path == second_path
    assert first_path.exists()

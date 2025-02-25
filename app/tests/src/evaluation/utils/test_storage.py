"""Tests for QA pair storage utilities."""

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_get_latest_version_race_condition(storage, sample_qa_pairs):
    """Test handling of race conditions in get_latest_version."""
    version1 = "20240219_test"
    version2 = "20240220_test"

    # Save first version
    storage.save_qa_pairs(sample_qa_pairs, version1)

    # Create a broken symlink to simulate race condition
    latest_link = storage.base_path / "latest"
    latest_link.unlink()
    nonexistent = storage.base_path / "nonexistent"
    latest_link.symlink_to(nonexistent)

    # Save second version - should handle broken symlink
    storage.save_qa_pairs(sample_qa_pairs, version2)

    # Get latest version should work and fix symlink
    latest = storage.get_latest_version()
    assert latest == version2
    assert latest_link.exists()
    assert latest_link.resolve().name == version2


def test_save_qa_pairs_io_error(storage, sample_qa_pairs, monkeypatch):
    """Test handling of IO errors during save."""
    version_id = "test_version"

    def mock_dump(*args, **kwargs):
        raise IOError("Simulated IO error")

    # Patch json.dump to simulate IO error
    monkeypatch.setattr(json, "dump", mock_dump)

    with pytest.raises(IOError):
        storage.save_qa_pairs(sample_qa_pairs, version_id)


def test_get_latest_version_multiple_symlink_errors(storage, sample_qa_pairs):
    """Test handling of multiple symlink errors in get_latest_version."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    latest_link = storage.base_path / "latest"
    latest_link.unlink()  # Remove existing symlink

    # Create a situation where symlink operations fail multiple times
    error_count = 0
    original_symlink_to = Path.symlink_to

    def mock_symlink_to(self, *args, **kwargs):
        nonlocal error_count
        error_count += 1
        if error_count <= 2:  # Fail twice
            raise OSError("Simulated symlink error")
        # Actually create the symlink on third try
        return original_symlink_to(self, *args, **kwargs)

    with patch.object(Path, "symlink_to", new=mock_symlink_to):
        # Should still succeed after retries
        latest = storage.get_latest_version()
        assert latest == version_id
        assert error_count == 3  # Should have tried exactly 3 times


def test_get_latest_version_no_symlink(storage, sample_qa_pairs):
    """Test getting latest version works even without symlink support."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Mock symlink operations to always fail
    def mock_symlink_to(*args, **kwargs):
        raise OSError("Symlinks not supported")

    with patch.object(Path, "symlink_to", side_effect=mock_symlink_to):
        # Should still get correct version even without symlink
        latest = storage.get_latest_version()
        assert latest == version_id


def test_save_qa_pairs_csv_error_handling(storage, sample_qa_pairs, monkeypatch):
    """Test handling of CSV writing errors."""
    version_id = "test_version"

    class MockWriter:
        def writeheader(self):
            pass

        def writerow(self, row):
            raise csv.Error("Simulated CSV error")

    def mock_dictwriter(*args, **kwargs):
        return MockWriter()

    # Patch csv.DictWriter to simulate CSV writing error
    monkeypatch.setattr(csv, "DictWriter", mock_dictwriter)

    with pytest.raises(csv.Error):
        storage.save_qa_pairs(sample_qa_pairs, version_id)


def test_get_version_metadata_corrupted_json(storage, sample_qa_pairs):
    """Test handling of corrupted metadata JSON file."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Corrupt the metadata file
    metadata_path = storage.get_version_path(version_id) / "metadata.json"
    with open(metadata_path, "w") as f:
        f.write("corrupted json{")

    with pytest.raises(json.JSONDecodeError):
        storage.get_version_metadata(version_id)


def test_update_symlink_max_retries(storage, sample_qa_pairs):
    """Test _update_symlink retries and eventually fails after max attempts."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Mock symlink_to to always fail
    with patch.object(Path, "symlink_to", side_effect=OSError("Simulated error")):
        with pytest.raises(OSError):
            storage._update_symlink(storage.base_path / version_id)


def test_update_symlink_cleanup(storage, sample_qa_pairs):
    """Test _update_symlink cleans up temp files even on failure."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Count how many temp files exist before and after
    def count_temp_links():
        return len([f for f in storage.base_path.iterdir() if f.name.startswith("latest.")])

    initial_count = count_temp_links()

    # Force a failure
    with patch.object(Path, "symlink_to", side_effect=OSError("Simulated error")):
        try:
            storage._update_symlink(storage.base_path / version_id)
        except OSError:
            pass

    # Should have same number of temp files as before
    assert count_temp_links() == initial_count


def test_update_symlink_retry_success(storage, sample_qa_pairs):
    """Test _update_symlink succeeds after initial failures."""
    version_id = "test_version"
    version_dir = storage.base_path / version_id
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    fail_count = [0]
    original_symlink_to = Path.symlink_to

    def mock_symlink_to(self, *args, **kwargs):
        if fail_count[0] < 2:  # Fail twice then succeed
            fail_count[0] += 1
            raise OSError("Mock symlink error")
        return original_symlink_to(self, *args, **kwargs)

    with patch.object(Path, "symlink_to", new=mock_symlink_to):
        storage._update_symlink(version_dir)
        assert (storage.base_path / "latest").resolve() == version_dir
        assert fail_count[0] == 2  # Verify it retried twice


def test_update_symlink_temp_cleanup_on_error(storage, sample_qa_pairs):
    """Test temporary symlinks are cleaned up even when update fails."""
    version_id = "test_version"
    version_dir = storage.base_path / version_id
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    def mock_rename(*args, **kwargs):
        raise OSError("Mock rename error")

    with (
        patch.object(Path, "rename", side_effect=mock_rename),
        pytest.raises(OSError, match="Mock rename error"),
    ):
        storage._update_symlink(version_dir)

    # Verify no temporary symlinks are left
    temp_links = [f for f in storage.base_path.iterdir() if f.name.startswith("latest.")]
    assert not temp_links


def test_get_version_metadata_json_error(storage, sample_qa_pairs):
    """Test get_version_metadata handles JSON parsing errors."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Corrupt the metadata file with invalid JSON
    metadata_path = storage.get_version_path(version_id) / "metadata.json"
    metadata_path.write_text("invalid{json")

    with pytest.raises(json.JSONDecodeError):
        storage.get_version_metadata(version_id)


def test_save_qa_pairs_csv_write_error(storage, sample_qa_pairs):
    """Test save_qa_pairs handles CSV writing errors."""
    version_id = "test_version"

    # Mock csv.DictWriter to raise error
    mock_writer = MagicMock()
    mock_writer.writeheader.side_effect = csv.Error("CSV write error")

    with patch("csv.DictWriter", return_value=mock_writer):
        with pytest.raises(csv.Error, match="CSV write error"):
            storage.save_qa_pairs(sample_qa_pairs, version_id)


def test_get_latest_version_empty_dir_with_latest(storage):
    """Test get_latest_version when only 'latest' symlink exists."""
    # Create latest symlink pointing nowhere
    latest_link = storage.base_path / "latest"
    nonexistent = storage.base_path / "nonexistent"
    latest_link.symlink_to(nonexistent, target_is_directory=True)

    with pytest.raises(ValueError, match="No QA pairs found"):
        storage.get_latest_version()


def test_save_qa_pairs_metadata_write_error(storage, sample_qa_pairs):
    """Test save_qa_pairs handles metadata writing errors."""
    version_id = "test_version"

    def mock_dump(*args, **kwargs):
        raise IOError("Metadata write error")

    with patch("json.dump", side_effect=mock_dump):
        with pytest.raises(IOError, match="Metadata write error"):
            storage.save_qa_pairs(sample_qa_pairs, version_id)


def test_save_qa_pairs_directory_creation_error(storage, sample_qa_pairs):
    """Test save_qa_pairs handles directory creation errors."""
    version_id = "test_version"

    # Mock mkdir to raise error
    with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
        with pytest.raises(OSError, match="Permission denied"):
            storage.save_qa_pairs(sample_qa_pairs, version_id)


def test_save_qa_pairs_symlink_resolution_mismatch(storage, sample_qa_pairs):
    """Test save_qa_pairs handles symlink resolution mismatch."""
    version_id = "test_version"

    # Create a symlink pointing to a different directory
    other_dir = storage.base_path / "other_dir"
    other_dir.mkdir()
    latest_link = storage.base_path / "latest"
    latest_link.symlink_to(other_dir, target_is_directory=True)

    # Save should succeed and update symlink
    csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id)
    assert latest_link.resolve() == csv_path.parent


def test_save_qa_pairs_symlink_update_error(storage, sample_qa_pairs):
    """Test save_qa_pairs handles symlink update errors."""
    version_id = "test_version"

    def mock_symlink_to(*args, **kwargs):
        raise OSError("Symlink error")

    with patch.object(Path, "symlink_to", side_effect=mock_symlink_to):
        # Should still save files even if symlink fails
        csv_path = storage.save_qa_pairs(sample_qa_pairs, version_id)
        assert csv_path.exists()


def test_get_latest_version_same_timestamp(storage, sample_qa_pairs):
    """Test get_latest_version with multiple versions having same timestamp."""
    # Create versions with same timestamp but different IDs
    versions = ["20240220_test1", "20240220_test2"]
    for version_id in versions:
        storage.save_qa_pairs(sample_qa_pairs, version_id)

    # Should get alphabetically last version
    latest = storage.get_latest_version()
    assert latest == "20240220_test2"


def test_get_latest_version_directory_error(storage, sample_qa_pairs):
    """Test get_latest_version handles directory iteration errors."""
    version_id = "test_version"
    storage.save_qa_pairs(sample_qa_pairs, version_id)

    def mock_iterdir(*args):
        raise OSError("Permission denied")

    with patch.object(Path, "iterdir", side_effect=mock_iterdir):
        with pytest.raises(ValueError, match="No QA pairs found"):
            storage.get_latest_version()


def test_get_version_path_not_directory(storage, sample_qa_pairs):
    """Test get_version_path when path exists but is not a directory."""
    version_id = "test_version"

    # Create a file instead of a directory
    version_path = storage.base_path / version_id
    version_path.write_text("not a directory")

    with pytest.raises(ValueError, match="Version .* not found"):
        storage.get_version_path(version_id)

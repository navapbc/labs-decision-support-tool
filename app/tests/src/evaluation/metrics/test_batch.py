"""Tests for batch processing functions."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.evaluation.metrics.batch import (
    create_batch_config,
    filter_questions,
    get_git_commit,
    get_package_version,
)


def test_get_git_commit():
    """Test getting git commit hash."""
    # Test successful case
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "abc123\n"
        assert get_git_commit() == "abc123"
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )

    # Test failure case
    with patch("subprocess.run", side_effect=Exception("git error")):
        try:
            get_git_commit()
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            assert "Failed to get git commit hash" in str(e)
            assert "git error" in str(e)


def test_get_package_version():
    """Test getting package version from actual file."""
    # Create a temporary pyproject.toml file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pyproject_path = temp_path / "pyproject.toml"

        # Write test content
        with open(pyproject_path, "w") as f:
            f.write('[tool.poetry]\nname = "app"\nversion = "1.0.0"\n')

        # Change to temp directory and test
        current_dir = os.getcwd()
        try:
            os.chdir(temp_dir)
            assert get_package_version() == "1.0.0"
        finally:
            os.chdir(current_dir)

        # Test malformed file
        with open(pyproject_path, "w") as f:
            f.write('[tool.poetry]\nname = "app"\nno_version_here\n')

        try:
            os.chdir(temp_dir)
            get_package_version()
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            assert "No version field found in pyproject.toml" in str(e)
        finally:
            os.chdir(current_dir)


def test_create_batch_config():
    """Test batch configuration creation."""
    # Only mock git commit, let package version use real file
    with patch("src.evaluation.metrics.batch.get_git_commit", return_value="abc123"):
        # Test with minimal parameters
        config = create_batch_config(k_value=5)
        assert config.evaluation_config.k_value == 5
        assert config.evaluation_config.num_samples == 0
        assert config.evaluation_config.dataset_filter == []
        assert config.software_info.git_commit == "abc123"
        assert config.batch_id is not None
        assert config.timestamp is not None

        # Test with all parameters
        config = create_batch_config(
            k_value=10,
            dataset_filter=["dataset1"],
            git_commit="def456",
        )
        assert config.evaluation_config.k_value == 10
        assert config.evaluation_config.dataset_filter == ["dataset1"]
        assert config.software_info.git_commit == "def456"


def test_filter_questions():
    """Test question filtering by dataset."""
    questions = [
        {"dataset": "Benefits Information Hub", "question": "q1"},
        {"dataset": "LA County Policy", "question": "q2"},
        {"dataset": "Other Dataset", "question": "q3"},
    ]

    # Test with no filter
    assert len(filter_questions(questions, None)) == 3

    # Test filtering single dataset
    filtered = filter_questions(questions, ["imagine_la"])
    assert len(filtered) == 1
    assert filtered[0]["question"] == "q1"

    # Test filtering multiple datasets
    filtered = filter_questions(questions, ["imagine_la", "la_policy"])
    assert len(filtered) == 2
    assert {q["question"] for q in filtered} == {"q1", "q2"}

    # Test filtering non-existent dataset
    filtered = filter_questions(questions, ["non_existent"])
    assert len(filtered) == 0

    # Test case sensitivity and mapping
    filtered = filter_questions(questions, ["IMAGINE_LA"])
    assert len(filtered) == 1
    assert filtered[0]["question"] == "q1"

    # Test with unknown dataset (should use original name)
    filtered = filter_questions(questions, ["Other Dataset"])
    assert len(filtered) == 1
    assert filtered[0]["question"] == "q3"

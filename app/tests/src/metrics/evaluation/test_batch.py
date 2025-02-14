"""Tests for batch processing functions."""

from unittest.mock import mock_open, patch

from src.metrics.evaluation.batch import (
    create_batch_config,
    filter_questions,
    get_git_commit,
    get_package_version,
    stratified_sample,
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
    """Test getting package version."""
    # Test successful case
    mock_toml = 'name = "app"\nversion = "1.0.0"\n'
    with patch("builtins.open", mock_open(read_data=mock_toml)):
        assert get_package_version() == "1.0.0"

    # Test file not found case
    with patch("builtins.open", side_effect=FileNotFoundError("No such file")):
        try:
            get_package_version()
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            assert "Failed to get package version" in str(e)
            assert "No such file" in str(e)

    # Test malformed file case
    mock_toml_bad = 'name = "app"\nno_version_here\n'
    with patch("builtins.open", mock_open(read_data=mock_toml_bad)):
        try:
            get_package_version()
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            assert "No version field found in pyproject.toml" in str(e)


def test_create_batch_config():
    """Test batch configuration creation."""
    # Mock git commit and package version
    with patch("src.metrics.evaluation.batch.get_git_commit", return_value="abc123"):
        with patch("src.metrics.evaluation.batch.get_package_version", return_value="1.0.0"):
            # Test with minimal parameters
            config = create_batch_config(k_value=5)
            assert config.k_value == 5
            assert config.num_samples == 0
            assert config.dataset_filter == []
            assert config.package_version == "1.0.0"
            assert config.git_commit == "abc123"
            assert config.batch_id is not None
            assert config.timestamp is not None

            # Test with all parameters
            config = create_batch_config(
                k_value=10,
                dataset_filter=["dataset1", "dataset2"],
                git_commit="test123",
            )
            assert config.k_value == 10
            assert config.dataset_filter == ["dataset1", "dataset2"]
            assert config.git_commit == "test123"  # Should use provided commit hash
            assert config.package_version == "1.0.0"
            assert config.batch_id is not None
            assert config.timestamp is not None

            # Test that git_commit is properly included in to_dict output
            config_dict = config.to_dict()
            assert config_dict["software_info"]["git_commit"] == "test123"


def test_stratified_sample():
    """Test stratified sampling of questions."""
    questions = [
        {"dataset": "dataset1", "question": "q1"},
        {"dataset": "dataset1", "question": "q2"},
        {"dataset": "dataset1", "question": "q3"},
        {"dataset": "dataset2", "question": "q4"},
        {"dataset": "dataset2", "question": "q5"},
    ]

    # Test with 100% sampling
    full_sample = stratified_sample(questions, 1.0)
    assert len(full_sample) == 5
    assert len([q for q in full_sample if q["dataset"] == "dataset1"]) == 3
    assert len([q for q in full_sample if q["dataset"] == "dataset2"]) == 2

    # Test with 50% sampling
    half_sample = stratified_sample(questions, 0.5)
    assert len(half_sample) >= 2  # At least min_per_dataset for each dataset
    dataset1_count = len([q for q in half_sample if q["dataset"] == "dataset1"])
    dataset2_count = len([q for q in half_sample if q["dataset"] == "dataset2"])
    assert dataset1_count >= 1
    assert dataset2_count >= 1

    # Test with very small sampling but respecting min_per_dataset
    min_sample = stratified_sample(questions, 0.1, min_per_dataset=1)
    assert len(min_sample) >= 2  # At least 1 per dataset
    assert len([q for q in min_sample if q["dataset"] == "dataset1"]) >= 1
    assert len([q for q in min_sample if q["dataset"] == "dataset2"]) >= 1

    # Test with random seed for reproducibility
    sample1 = stratified_sample(questions, 0.5, random_seed=42)
    sample2 = stratified_sample(questions, 0.5, random_seed=42)
    assert [q["question"] for q in sample1] == [q["question"] for q in sample2]

    # Test that random seed is properly reset
    import random

    random.seed(123)
    val1 = random.random()
    stratified_sample(questions, 0.5, random_seed=42)
    random.seed(123)
    val2 = random.random()
    assert val1 == val2  # Random state should be restored


def test_filter_questions():
    """Test question filtering by dataset."""
    questions = [
        {"dataset": "Imagine LA", "question": "q1"},
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

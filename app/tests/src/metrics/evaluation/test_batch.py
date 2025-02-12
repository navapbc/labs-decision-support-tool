"""Tests for batch processing functions."""

from src.metrics.evaluation.batch import create_batch_config, filter_questions, stratified_sample


def test_create_batch_config():
    """Test batch configuration creation."""
    # Test with minimal parameters
    config = create_batch_config(k_value=5)
    assert config.k_value == 5
    assert config.num_samples == 0
    assert config.dataset_filter == []
    assert config.package_version is not None
    assert config.git_commit is not None
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
    assert config.git_commit == "test123"


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

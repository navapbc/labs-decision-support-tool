"""Tests for evaluation runner."""

import csv
import json
import uuid
from pathlib import Path

import pytest

from src.evaluation.metrics.runner import EvaluationRunner, run_evaluation


@pytest.fixture
def mock_questions():
    """Create mock questions data."""
    unique_dataset1 = f"test_dataset_{uuid.uuid4()}"
    unique_dataset2 = f"test_dataset_{uuid.uuid4()}"
    return [
        {
            "id": "1",
            "question": "test question 1?",
            "answer": "test answer 1",
            "dataset": unique_dataset1,
            "document_name": "doc1",
            "document_source": "source1",
            "expected_chunk_content": "chunk content 1",
        },
        {
            "id": "2",
            "question": "test question 2?",
            "answer": "test answer 2",
            "dataset": unique_dataset2,
            "document_name": "doc2",
            "document_source": "source2",
            "expected_chunk_content": "chunk content 2",
        },
    ]


@pytest.fixture
def mock_git_commit():
    """Mock the git commit function."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("src.evaluation.metrics.batch.get_git_commit", lambda: "test-commit-hash")
        yield


def test_evaluation_runner_init():
    """Test EvaluationRunner initialization."""
    runner = EvaluationRunner(log_dir="logs/evaluations")
    assert runner.log_dir == "logs/evaluations"


def test_load_questions_success(mock_questions, tmp_path):
    """Test successful loading of questions from CSV."""
    runner = EvaluationRunner(log_dir="logs/evaluations")
    questions_file = tmp_path / "test_questions.csv"

    # Create actual CSV file
    with open(questions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=mock_questions[0].keys())
        writer.writeheader()
        writer.writerows(mock_questions)

    # Load questions from file
    questions = runner.load_questions(str(questions_file))
    assert len(questions) == 2
    assert questions[0]["id"] == "1"
    assert questions[0]["question"] == "test question 1?"
    assert questions[0]["dataset"].startswith("test_dataset_")


def test_load_questions_file_not_found(tmp_path):
    """Test loading questions from non-existent file."""
    runner = EvaluationRunner(log_dir="logs/evaluations")
    nonexistent_file = tmp_path / "nonexistent.csv"

    with pytest.raises(RuntimeError, match="Error loading questions"):
        runner.load_questions(str(nonexistent_file))


def test_run_evaluation_batch(mock_questions, mock_git_commit, tmp_path):
    """Test running a single evaluation batch."""
    log_dir = tmp_path / "eval_logs"
    runner = EvaluationRunner(log_dir=str(log_dir))

    # Run batch
    runner.run_evaluation_batch(mock_questions, k=5)

    # Verify logs were created
    batch_files = list(Path(log_dir).glob("*/batch_*.json"))
    assert len(batch_files) == 1

    results_files = list(Path(log_dir).glob("*/results_*.jsonl"))
    assert len(results_files) == 1

    metrics_files = list(Path(log_dir).glob("*/metrics_*.json"))
    assert len(metrics_files) == 1


def test_run_evaluation_with_filtering(mock_questions, mock_git_commit, tmp_path):
    """Test running evaluation with dataset filtering."""
    log_dir = tmp_path / "eval_logs"
    runner = EvaluationRunner(log_dir=str(log_dir))

    # Create questions file
    questions_file = tmp_path / "test.csv"
    with open(questions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=mock_questions[0].keys())
        writer.writeheader()
        writer.writerows(mock_questions)

    # Run evaluation with dataset filter - use the first dataset from mock_questions
    dataset_to_filter = mock_questions[0]["dataset"]
    runner.run_evaluation(
        questions_file=str(questions_file), k_values=[5], dataset_filter=[dataset_to_filter]
    )

    # Verify logs were created
    batch_files = list(Path(log_dir).glob("*/batch_*.json"))
    assert len(batch_files) == 1

    results_files = list(Path(log_dir).glob("*/results_*.jsonl"))
    assert len(results_files) == 1

    # Verify only dataset1 questions were processed
    with open(results_files[0]) as f:
        results = [json.loads(line) for line in f]
        assert len(results) == 1  # Only one question from dataset1
        assert results[0]["expected_chunk"]["source"] == dataset_to_filter


def test_run_evaluation_no_questions(tmp_path):
    """Test running evaluation with no questions after filtering."""
    log_dir = tmp_path / "eval_logs"
    runner = EvaluationRunner(log_dir=str(log_dir))

    # Create empty questions file
    questions_file = tmp_path / "test.csv"
    with open(questions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "question", "answer", "dataset"])
        writer.writeheader()

    with pytest.raises(ValueError, match="No questions to evaluate"):
        runner.run_evaluation(questions_file=str(questions_file), k_values=[5])


def test_run_evaluation_batch_error_handling(mock_questions, mock_git_commit, tmp_path):
    """Test error handling in evaluation batch."""
    log_dir = tmp_path / "eval_logs"
    runner = EvaluationRunner(log_dir=str(log_dir))

    # Test batch processing error by providing invalid questions
    invalid_questions = [{"id": "1"}]  # Missing required fields

    with pytest.raises(
        KeyError
    ):  # batch_process_results will raise KeyError for missing 'question'
        runner.run_evaluation_batch(invalid_questions, k=5)

    # Verify no log files were created due to error
    # The logger's __exit__ should clean up any partial files
    assert not list(Path(log_dir).glob("*/batch_*.json"))
    assert not list(Path(log_dir).glob("*/results_*.jsonl"))
    assert not list(Path(log_dir).glob("*/metrics_*.json"))


def test_convenience_function(mock_git_commit, tmp_path):
    """Test the convenience function run_evaluation."""
    log_dir = tmp_path / "eval_logs"
    questions_file = tmp_path / "test.csv"

    # Create test questions file with unique dataset name
    unique_dataset = f"test_dataset_{uuid.uuid4()}"
    questions = [
        {
            "id": "1",
            "question": "test?",
            "answer": "test",
            "dataset": unique_dataset,
            "document_name": "doc1",
            "document_source": "source1",
            "expected_chunk_content": "content1",
        }
    ]

    with open(questions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=questions[0].keys())
        writer.writeheader()
        writer.writerows(questions)

    # Run evaluation with the unique dataset
    run_evaluation(
        questions_file=str(questions_file),
        k_values=[5],
        dataset_filter=[unique_dataset],
        sample_fraction=0.5,
        random_seed=42,
        log_dir=str(log_dir),
        commit="test123",
    )

    # Verify logs were created
    batch_files = list(Path(log_dir).glob("*/batch_*.json"))
    assert len(batch_files) == 1

    results_files = list(Path(log_dir).glob("*/results_*.jsonl"))
    assert len(results_files) == 1

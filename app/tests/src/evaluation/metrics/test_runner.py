"""Tests for evaluation runner."""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.db.models.document import ChunkWithScore
from src.evaluation.metrics.runner import EvaluationRunner, run_evaluation
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


@pytest.fixture
def mock_git_commit():
    """Mock git commit hash."""
    with patch("src.evaluation.metrics.batch.get_git_commit", return_value="test123"):
        yield


@pytest.fixture
def mock_datetime():
    """Mock datetime to return a fixed date."""
    with patch("src.evaluation.metrics.logging.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1)
        yield mock_dt


@pytest.fixture
def test_document():
    """Create a test document with chunks."""
    document = DocumentFactory.build(
        name="test_doc",
        content="Test document content",
        source="test_dataset",
        dataset="dataset1",
    )
    chunk = ChunkFactory.build(
        document=document,
        content="test chunk content",
    )
    document.chunks = [chunk]
    return document


@pytest.fixture
def test_questions_csv(tmp_path, test_document):
    """Create a temporary CSV file with test questions."""
    questions = [
        {
            "id": "1",
            "question": "test question 1?",
            "answer": "test answer 1",
            "dataset": "dataset1",
            "document_name": test_document.name,
            "chunk_id": str(test_document.chunks[0].id),
            "expected_chunk_content": test_document.chunks[0].content,
        },
        {
            "id": "2",
            "question": "test question 2?",
            "answer": "test answer 2",
            "dataset": "dataset2",
            "document_name": "other_doc",
            "chunk_id": "chunk2",
            "expected_chunk_content": "other content",
        },
    ]

    # Create CSV file
    csv_path = tmp_path / "test_questions.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=questions[0].keys())
        writer.writeheader()
        writer.writerows(questions)

    return str(csv_path)


def create_mock_retrieval_func(test_document):
    """Create a mock retrieval function that returns the test document's chunk."""

    def retrieval_func(query: str, k: int):
        chunk = test_document.chunks[0]
        return [ChunkWithScore(chunk=chunk, score=0.85)]

    return retrieval_func


def find_log_files(log_dir: Path) -> tuple[Path, Path, Path]:
    """Find batch config, results, and metrics files in log directory including date subdirectories."""
    # Use the known date directory ""2024-01-01"
    log_dir = log_dir / "2024-01-01"
    if not log_dir.exists():
        return None, None, None

    batch_file = next(log_dir.glob("batch_*.json"), None)
    results_file = next(log_dir.glob("results_*.jsonl"), None)
    metrics_file = next(log_dir.glob("metrics_*.json"), None)
    return batch_file, results_file, metrics_file


def test_evaluation_runner_init(test_document):
    """Test EvaluationRunner initialization."""
    retrieval_func = create_mock_retrieval_func(test_document)
    runner = EvaluationRunner(retrieval_func)
    assert runner.retrieval_func == retrieval_func
    assert runner.log_dir == "logs/evaluations"


def test_load_questions_success(test_questions_csv):
    """Test successful loading of questions from CSV."""
    runner = EvaluationRunner(lambda x, y: [])
    questions = runner.load_questions(test_questions_csv)

    assert len(questions) == 2
    assert questions[0]["id"] == "1"
    assert questions[0]["question"] == "test question 1?"
    assert questions[0]["dataset"] == "dataset1"


def test_load_questions_file_not_found():
    """Test loading questions from non-existent file."""
    runner = EvaluationRunner(lambda x, y: [])
    with pytest.raises(RuntimeError, match="Error loading questions"):
        runner.load_questions("nonexistent.csv")


def test_run_evaluation_batch(
    test_document, test_questions_csv, tmp_path, mock_git_commit, mock_datetime
):
    """Test running a single evaluation batch."""
    # Set up runner with real retrieval function
    retrieval_func = create_mock_retrieval_func(test_document)
    log_dir = tmp_path / "eval_logs"
    os.makedirs(log_dir, exist_ok=True)
    runner = EvaluationRunner(retrieval_func, str(log_dir))

    # Load questions and run batch
    questions = runner.load_questions(test_questions_csv)
    runner.run_evaluation_batch(questions, k=5)

    # Find and verify log files
    batch_file, results_file, metrics_file = find_log_files(log_dir)
    assert all(f is not None for f in (batch_file, results_file, metrics_file))

    # Verify file contents
    with open(batch_file) as f:
        batch_data = json.load(f)
        assert batch_data["evaluation_config"]["k_value"] == 5

    with open(results_file) as f:
        results = [line for line in f if line.strip()]
        assert len(results) == 2  # Should have processed both questions

    with open(metrics_file) as f:
        metrics_data = json.load(f)
        assert "overall_metrics" in metrics_data


def test_run_evaluation_with_filtering(
    test_document, test_questions_csv, tmp_path, mock_git_commit, mock_datetime
):
    """Test running evaluation with dataset filtering."""
    retrieval_func = create_mock_retrieval_func(test_document)
    log_dir = tmp_path / "eval_logs_filter"
    os.makedirs(log_dir, exist_ok=True)
    runner = EvaluationRunner(retrieval_func, str(log_dir))

    # Run evaluation with dataset filter
    runner.run_evaluation(
        questions_file=test_questions_csv,
        k_values=[5],
        dataset_filter=["dataset1"],
    )

    # Find and verify results file
    _, results_file, _ = find_log_files(log_dir)
    assert results_file is not None

    # Check that only dataset1 questions were processed
    with open(results_file) as f:
        results = [line for line in f if line.strip()]
        assert len(results) == 1  # Should only have processed one question
        result_data = json.loads(results[0])
        assert result_data["dataset"] == "dataset1"


def test_run_evaluation_with_sampling(
    test_document, test_questions_csv, tmp_path, mock_git_commit, mock_datetime
):
    """Test running evaluation with sampling."""
    retrieval_func = create_mock_retrieval_func(test_document)
    log_dir = tmp_path / "eval_logs_sample"
    os.makedirs(log_dir, exist_ok=True)
    runner = EvaluationRunner(retrieval_func, str(log_dir))

    # Run evaluation with sampling
    runner.run_evaluation(
        questions_file=test_questions_csv,
        k_values=[5],
        sample_fraction=0.5,
        random_seed=42,  # For reproducibility
    )

    # Find and verify results file
    _, results_file, _ = find_log_files(log_dir)
    assert results_file is not None

    # Verify results - should have sampled at least one question per dataset
    with open(results_file) as f:
        results = [line for line in f if line.strip()]
        assert len(results) >= 2  # Should have at least one per dataset
        datasets = {json.loads(r)["dataset"] for r in results}
        assert len(datasets) == 2  # Should have both datasets


def test_run_evaluation_no_questions(tmp_path):
    """Test running evaluation with no questions after filtering."""
    # Create empty questions file
    questions_file = tmp_path / "empty.csv"
    with open(questions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "question", "answer", "dataset"])
        writer.writeheader()

    runner = EvaluationRunner(lambda x, y: [])
    with pytest.raises(ValueError, match="No questions to evaluate"):
        runner.run_evaluation(questions_file=str(questions_file), k_values=[5])


def test_run_evaluation_batch_error_handling(
    test_document, test_questions_csv, tmp_path, mock_git_commit, mock_datetime
):
    """Test error handling in evaluation batch."""
    log_dir = tmp_path / "eval_logs_error"
    os.makedirs(log_dir, exist_ok=True)

    # Test with failing retrieval function
    def failing_retrieval_func(query: str, k: int):
        raise Exception("Test error")

    runner = EvaluationRunner(failing_retrieval_func, str(log_dir))
    questions = runner.load_questions(test_questions_csv)

    with pytest.raises(Exception, match="Test error"):
        runner.run_evaluation_batch(questions, k=5)

    # Verify log directory exists but contains no files or subdirectories
    # (everything should be cleaned up by the logger's __exit__)
    assert log_dir.exists()

    # Check for any files in the directory tree
    def has_files(directory):
        for path in directory.rglob("*"):
            if path.is_file():
                return True
        return False

    assert not has_files(log_dir), f"Found files in {log_dir} when there should be none"


def test_convenience_function(
    test_document, test_questions_csv, tmp_path, mock_git_commit, mock_datetime
):
    """Test the convenience function run_evaluation."""
    retrieval_func = create_mock_retrieval_func(test_document)
    log_dir = tmp_path / "eval_logs_convenience"
    os.makedirs(log_dir, exist_ok=True)

    # Run evaluation through convenience function
    run_evaluation(
        questions_file=test_questions_csv,
        k_values=[5],
        retrieval_func=retrieval_func,
        dataset_filter=["dataset1"],
        sample_fraction=0.5,
        random_seed=42,
        log_dir=str(log_dir),
        commit="test123",
    )

    # Find and verify log files
    batch_file, results_file, metrics_file = find_log_files(log_dir)
    assert all(f is not None for f in (batch_file, results_file, metrics_file))

    # Verify results file contains filtered data
    with open(results_file) as f:
        results = [line for line in f if line.strip()]
        assert len(results) > 0
        for result in results:
            result_data = json.loads(result)
            assert result_data["dataset"] == "dataset1"

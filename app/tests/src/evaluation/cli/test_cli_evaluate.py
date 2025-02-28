"""Tests for the evaluate CLI module."""

import argparse
import csv
import uuid
from pathlib import Path

import pytest

from src.evaluation.cli import evaluate


@pytest.fixture
def mock_git_commit():
    """Mock the git commit function."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("src.evaluation.metrics.batch.get_git_commit", lambda: "test-commit-hash")
        yield


@pytest.fixture
def questions_file(tmp_path):
    """Create a test questions file."""
    unique_dataset1 = f"test_dataset_imagine_la_{uuid.uuid4()}"
    unique_dataset2 = f"test_dataset_dpss_policy_{uuid.uuid4()}"
    questions = [
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

    qa_pairs_dir = tmp_path / "qa_pairs"
    qa_pairs_dir.mkdir(parents=True)
    questions_path = qa_pairs_dir / "qa_pairs.csv"

    with open(questions_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=questions[0].keys())
        writer.writeheader()
        writer.writerows(questions)

    return questions_path


def test_create_parser(tmp_path):
    """Test that the parser is created correctly."""
    parser = evaluate.create_parser()
    assert isinstance(parser, argparse.ArgumentParser)

    # Test default values
    args = parser.parse_args([])
    assert args.dataset is None
    assert args.k == [5, 10, 25]
    assert args.qa_pairs_version is None
    assert isinstance(args.output_dir, Path)
    assert args.sampling is None
    assert args.random_seed is None
    assert args.commit is None

    # Test parsing of all arguments
    test_output = tmp_path / "custom_output"
    unique_dataset = f"test_dataset_imagine_la_{uuid.uuid4()}"
    args = parser.parse_args(
        [
            "--dataset",
            unique_dataset,
            "--k",
            "5",
            "10",
            "--qa-pairs-version",
            "v1",
            "--output-dir",
            str(test_output),
            "--sampling",
            "0.5",
            "--random-seed",
            "42",
            "--commit",
            "abc123",
        ]
    )
    assert args.dataset == [unique_dataset]
    assert args.k == [5, 10]
    assert args.qa_pairs_version == "v1"
    assert args.output_dir == test_output
    assert args.sampling == 0.5
    assert args.random_seed == 42
    assert args.commit == "abc123"


def test_main_with_dataset(questions_file, mock_git_commit, tmp_path):
    """Test the main function with a dataset specified."""
    output_dir = tmp_path / "logs" / "evaluations"
    
    # Read the first dataset name from the questions file
    with open(questions_file, "r") as f:
        reader = csv.DictReader(f)
        first_row = next(reader)
        dataset_to_filter = first_row["dataset"]
    
    test_args = [
        "evaluate.py",
        "--dataset",
        dataset_to_filter,
        "--k",
        "5",
        "10",
        "--output-dir",
        str(tmp_path),
    ]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("sys.argv", test_args)
        evaluate.main()

        # Verify that evaluation logs were created
        assert output_dir.exists()

        # Check for batch files
        batch_files = list(output_dir.glob("*/batch_*.json"))
        assert len(batch_files) > 0

        # Check for results files
        results_files = list(output_dir.glob("*/results_*.jsonl"))
        assert len(results_files) > 0


def test_main_with_sampling(questions_file, mock_git_commit, tmp_path):
    """Test the main function with sampling specified."""
    output_dir = tmp_path / "logs" / "evaluations"
    test_args = [
        "evaluate.py",
        "--sampling",
        "0.5",
        "--random-seed",
        "42",
        "--output-dir",
        str(tmp_path),
    ]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("sys.argv", test_args)
        evaluate.main()

        # Verify that evaluation logs were created
        assert output_dir.exists()

        # Check for batch files
        batch_files = list(output_dir.glob("*/batch_*.json"))
        assert len(batch_files) > 0

        # Check for results files
        results_files = list(output_dir.glob("*/results_*.jsonl"))
        assert len(results_files) > 0


def test_main_error_handling(tmp_path):
    """Test error handling in the main function."""
    # Use a non-existent questions file to trigger an error
    test_args = ["evaluate.py", "--output-dir", str(tmp_path)]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("sys.argv", test_args)
        with pytest.raises(RuntimeError, match="Error loading questions"):
            evaluate.main()

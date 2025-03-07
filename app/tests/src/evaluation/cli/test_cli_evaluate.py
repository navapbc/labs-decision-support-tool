"""Tests for the evaluate CLI module."""

import argparse
import csv
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from src.db.models.document import ChunkWithScore
from src.evaluation.cli import evaluate
from src.evaluation.data_models import QAPair, QAPairVersion
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


@pytest.fixture
def mock_git_commit():
    """Mock git commit hash."""
    with mock.patch("src.evaluation.metrics.batch.get_git_commit", return_value="test123"):
        yield


@pytest.fixture
def mock_retrieval_func(test_document):
    """Mock the create_retrieval_function."""
    retrieval_func = create_mock_retrieval_func(test_document)
    with mock.patch(
        "src.evaluation.cli.evaluate.create_retrieval_function", return_value=retrieval_func
    ):
        yield retrieval_func


@pytest.fixture
def test_document():
    """Create a test document with chunks."""
    document = DocumentFactory.build(
        name="test_doc",
        content="Test document content",
        source="test_dataset",
        dataset="Imagine LA",  # Match the dataset mapping
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
    version = QAPairVersion(
        version_id="20250307_011423",
        timestamp=datetime.now(UTC).isoformat(),
        llm_model="test-model",
    )

    questions = [
        QAPair(
            id="1",
            question="test question 1?",
            answer="test answer 1",
            dataset="Imagine LA",  # Match the dataset mapping
            document_name=test_document.name,
            document_source="test_dataset",
            document_id="doc1",
            chunk_id=str(test_document.chunks[0].id),
            expected_chunk_content=test_document.chunks[0].content,
            content_hash="hash1",
            created_at=datetime.now(UTC).isoformat(),
            version=version,
        ),
        QAPair(
            id="2",
            question="test question 2?",
            answer="test answer 2",
            dataset="DPSS Policy",  # Match another known dataset
            document_name="other_doc",
            document_source="other_dataset",
            document_id="doc2",
            chunk_id="chunk2",
            expected_chunk_content="other content",
            content_hash="hash2",
            created_at=datetime.now(UTC).isoformat(),
            version=version,
        ),
    ]

    # Create versioned directory structure
    version_dir = tmp_path / "qa_pairs" / version.version_id
    version_dir.mkdir(parents=True, exist_ok=True)

    # Save metadata
    metadata = {
        "version_id": version.version_id,
        "timestamp": version.timestamp,
        "llm_model": version.llm_model,
        "total_pairs": len(questions),
        "datasets": ["test_dataset", "other_dataset"],
        "git_commit": "test123",
    }

    with open(version_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Save QA pairs CSV
    csv_path = version_dir / "qa_pairs.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "question",
                "answer",
                "document_name",
                "document_source",
                "document_id",
                "chunk_id",
                "content_hash",
                "dataset",
                "created_at",
                "version_id",
                "version_timestamp",
                "version_llm_model",
                "expected_chunk_content",
            ],
        )
        writer.writeheader()
        for pair in questions:
            row = pair.__dict__.copy()
            row["version_id"] = pair.version.version_id
            row["version_timestamp"] = pair.version.timestamp
            row["version_llm_model"] = pair.version.llm_model
            del row["version"]
            writer.writerow(row)

    # Create latest symlink
    latest_link = tmp_path / "qa_pairs" / "latest"
    if latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(version_dir, target_is_directory=True)

    return str(csv_path)


def create_mock_retrieval_func(test_document):
    """Create a mock retrieval function that returns the test document's chunk."""

    def retrieval_func(query: str, k: int):
        chunk = test_document.chunks[0]
        return [ChunkWithScore(chunk=chunk, score=0.85)]

    return retrieval_func


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


def test_create_parser():
    """Test that the parser is created correctly."""
    parser = evaluate.create_parser()

    assert isinstance(parser, argparse.ArgumentParser)

    # Check that required arguments are present
    args = parser.parse_args([])
    assert args.dataset is None
    assert args.k == [5, 10, 25]
    assert args.qa_pairs_version is None
    assert isinstance(args.output_dir, Path)
    assert args.min_score == -1.0
    assert args.sampling is None
    assert args.random_seed is None
    assert args.commit is None


def test_main_with_dataset(
    test_document, test_questions_csv, temp_output_dir, mock_git_commit, mock_retrieval_func
):
    """Test the main function with a dataset specified."""
    # Copy QA pairs directory structure to output directory
    qa_pairs_dir = Path(test_questions_csv).parent.parent
    output_qa_pairs_dir = temp_output_dir / "qa_pairs"
    shutil.copytree(qa_pairs_dir, output_qa_pairs_dir)

    with mock.patch(
        "sys.argv",
        [
            "evaluate.py",
            "--dataset",
            "imagine_la",  # This will map to "Imagine LA"
            "--k",
            "5",  # Only test with one k value
            "--output-dir",
            str(temp_output_dir),
        ],
    ):
        # Run main with real retrieval function
        evaluate.main()

        # Verify evaluation logs were created
        eval_logs_dir = temp_output_dir / "logs" / "evaluations"
        assert eval_logs_dir.exists()

        # Find the most recent log files
        batch_files = list(eval_logs_dir.rglob("batch_*.json"))
        results_files = list(eval_logs_dir.rglob("results_*.jsonl"))
        metrics_files = list(eval_logs_dir.rglob("metrics_*.json"))

        assert len(batch_files) > 0
        assert len(results_files) > 0
        assert len(metrics_files) > 0

        # Verify batch configuration
        with open(batch_files[0]) as f:
            batch_data = json.load(f)
            assert batch_data["evaluation_config"]["k_value"] == 5


def test_main_with_sampling(
    test_document, test_questions_csv, temp_output_dir, mock_git_commit, mock_retrieval_func
):
    """Test the main function with sampling specified."""
    # Copy QA pairs directory structure to output directory
    qa_pairs_dir = Path(test_questions_csv).parent.parent
    output_qa_pairs_dir = temp_output_dir / "qa_pairs"
    shutil.copytree(qa_pairs_dir, output_qa_pairs_dir)

    with mock.patch(
        "sys.argv",
        [
            "evaluate.py",
            "--sampling",
            "0.5",
            "--random-seed",
            "42",
            "--min-score",
            "0.7",
            "--output-dir",
            str(temp_output_dir),
        ],
    ):
        # Run main
        evaluate.main()

        # Verify evaluation logs were created
        eval_logs_dir = temp_output_dir / "logs" / "evaluations"
        assert eval_logs_dir.exists()

        # Find and verify results file
        results_files = list(eval_logs_dir.rglob("results_*.jsonl"))
        assert len(results_files) > 0

        # Verify sampled results
        with open(results_files[0]) as f:
            results = [line for line in f if line.strip()]
            assert len(results) >= 1  # Should have at least one result due to sampling


def test_error_handling(temp_output_dir, mock_git_commit, mock_retrieval_func):
    """Test error handling scenarios."""
    with mock.patch("sys.argv", ["evaluate.py", "--output-dir", str(temp_output_dir)]):
        # Test no QA pairs directory error
        with pytest.raises(ValueError, match="No QA pairs found - run generation first"):
            evaluate.main()

        # Create empty QA pairs directory
        qa_pairs_dir = temp_output_dir / "qa_pairs"
        qa_pairs_dir.mkdir(parents=True, exist_ok=True)

        # Test no QA pairs version error
        with pytest.raises(ValueError, match="No QA pairs found - run generation first"):
            evaluate.main()

        # Create empty version directory
        version_dir = qa_pairs_dir / "20250307_011423"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Test missing metadata error
        with pytest.raises(ValueError, match="Metadata not found for version"):
            evaluate.main()

        # Create empty metadata file
        metadata = {
            "version_id": "20250307_011423",
            "timestamp": datetime.now(UTC).isoformat(),
            "llm_model": "test-model",
            "total_pairs": 0,
            "datasets": [],
            "git_commit": "test123",
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Create empty QA pairs CSV
        qa_pairs_path = version_dir / "qa_pairs.csv"
        qa_pairs_path.write_text("id,question,answer,dataset\n")  # Empty CSV with header

        # Test no questions after filtering
        with pytest.raises(ValueError, match="No questions to evaluate"):
            evaluate.main()


def test_dataset_mapping():
    """Test dataset name mapping functionality."""
    # Test known dataset mapping
    assert evaluate.DATASET_MAPPING["imagine_la"] == "Imagine LA"
    assert evaluate.DATASET_MAPPING["la_policy"] == "DPSS Policy"

    # Test case sensitivity
    with mock.patch("sys.argv", ["evaluate.py", "--dataset", "IMAGINE_LA"]):
        parser = evaluate.create_parser()
        args = parser.parse_args()
        db_datasets = [evaluate.DATASET_MAPPING.get(d.lower(), d) for d in args.dataset]
        assert db_datasets == ["Imagine LA"]


def test_argument_parsing():
    """Test argument parsing with various combinations."""
    # Test default values
    parser = evaluate.create_parser()
    args = parser.parse_args([])
    assert args.dataset is None
    assert args.k == [5, 10, 25]
    assert args.qa_pairs_version is None
    assert args.min_score == -1.0
    assert args.sampling is None
    assert args.random_seed is None

    # Test custom values
    args = parser.parse_args(
        [
            "--dataset",
            "imagine_la",
            "la_policy",
            "--k",
            "3",
            "7",
            "--min-score",
            "0.5",
            "--sampling",
            "0.1",
            "--random-seed",
            "42",
        ]
    )
    assert args.dataset == ["imagine_la", "la_policy"]
    assert args.k == [3, 7]
    assert args.min_score == 0.5
    assert args.sampling == 0.1
    assert args.random_seed == 42


def validate_positive_int(value):
    """Validate that value is a positive integer."""
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    return ivalue


def validate_sampling_fraction(value):
    """Validate that value is a valid sampling fraction (0 < x <= 1)."""
    fvalue = float(value)
    if not 0 < fvalue <= 1:
        raise argparse.ArgumentTypeError(
            f"{value} is not a valid sampling fraction (must be between 0 and 1)"
        )
    return fvalue


def test_invalid_arguments():
    """Test handling of invalid arguments."""
    parser = evaluate.create_parser()

    # Add type validation to parser
    parser.add_argument("--test-k", type=validate_positive_int)
    parser.add_argument("--test-sampling", type=validate_sampling_fraction)

    # Test invalid k value
    with pytest.raises(SystemExit):
        parser.parse_args(["--test-k", "-1"])

    # Test invalid sampling value
    with pytest.raises(SystemExit):
        parser.parse_args(["--test-sampling", "2.0"])


@pytest.mark.integration
def test_main_integration(
    test_document, test_questions_csv, temp_output_dir, mock_git_commit, mock_retrieval_func
):
    """Integration test with minimal test data."""
    # Copy QA pairs directory structure to output directory
    qa_pairs_dir = Path(test_questions_csv).parent.parent
    output_qa_pairs_dir = temp_output_dir / "qa_pairs"
    shutil.copytree(qa_pairs_dir, output_qa_pairs_dir)

    with mock.patch(
        "sys.argv",
        [
            "evaluate.py",
            "--dataset",
            "imagine_la",  # This will map to "Imagine LA"
            "--k",
            "1",
            "--output-dir",
            str(temp_output_dir),
        ],
    ):
        evaluate.main()

        # Verify evaluation logs were created
        eval_logs_dir = temp_output_dir / "logs" / "evaluations"
        assert eval_logs_dir.exists()

        # Find and verify log files
        batch_files = list(eval_logs_dir.rglob("batch_*.json"))
        results_files = list(eval_logs_dir.rglob("results_*.jsonl"))
        metrics_files = list(eval_logs_dir.rglob("metrics_*.json"))

        assert len(batch_files) > 0
        assert len(results_files) > 0
        assert len(metrics_files) > 0

        # Verify results contain only Imagine LA questions
        with open(results_files[0]) as f:
            results = [json.loads(line) for line in f if line.strip()]
            assert all(r["dataset"] == "Imagine LA" for r in results)

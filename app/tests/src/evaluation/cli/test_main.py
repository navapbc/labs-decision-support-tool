"""Tests for evaluation CLI main module."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.cli.main import DATASET_MAPPING, create_parser, main
from src.evaluation.qa_generation.config import GenerationConfig


@pytest.fixture
def parser():
    """Create argument parser for testing."""
    return create_parser()


def test_create_parser():
    """Test argument parser creation and structure."""
    parser = create_parser()

    # Test basic parser structure
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.description == "QA Generation and Evaluation Tools"

    # Get subparsers
    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    subparsers = subparsers_action.choices

    # Test generate subparser
    assert "generate" in subparsers
    gen_parser = subparsers["generate"]

    # Check generate command arguments
    gen_args = {action.dest: action for action in gen_parser._actions if action.dest != "help"}
    assert "dataset" in gen_args
    assert "sampling" in gen_args
    assert "random_seed" in gen_args
    assert "output_dir" in gen_args
    assert "llm" in gen_args
    assert "commit" in gen_args

    # Test evaluate subparser
    assert "evaluate" in subparsers
    eval_parser = subparsers["evaluate"]

    # Check evaluate command arguments
    eval_args = {action.dest: action for action in eval_parser._actions if action.dest != "help"}
    assert "dataset" in eval_args
    assert "k" in eval_args
    assert "qa_pairs_version" in eval_args
    assert "output_dir" in eval_args
    assert "min_score" in eval_args
    assert "sampling" in eval_args
    assert "random_seed" in eval_args
    assert "commit" in eval_args


def test_parser_generate_defaults(parser):
    """Test default values for generate command."""
    args = parser.parse_args(["generate"])

    assert args.command == "generate"
    assert args.dataset is None
    assert args.sampling is None
    assert args.random_seed is None
    assert args.output_dir == Path("src/evaluation/data")
    assert args.llm == "gpt-4o-mini"
    assert args.commit is None


def test_parser_evaluate_defaults(parser):
    """Test default values for evaluate command."""
    args = parser.parse_args(["evaluate"])

    assert args.command == "evaluate"
    assert args.dataset is None
    assert args.k == [5, 10, 25]
    assert args.qa_pairs_version is None
    assert args.output_dir == Path("src/evaluation/data")
    assert args.min_score == -1.0
    assert args.sampling is None
    assert args.random_seed is None
    assert args.commit is None


def test_parser_generate_with_args(parser):
    """Test parsing generate command with arguments."""
    args = parser.parse_args(
        [
            "generate",
            "--dataset",
            "imagine_la",
            "la_policy",
            "--sampling",
            "0.1",
            "--random-seed",
            "42",
            "--output-dir",
            "custom/output",
            "--llm",
            "custom-model",
            "--commit",
            "abc123",
        ]
    )

    assert args.command == "generate"
    assert args.dataset == ["imagine_la", "la_policy"]
    assert args.sampling == 0.1
    assert args.random_seed == 42
    assert args.output_dir == Path("custom/output")
    assert args.llm == "custom-model"
    assert args.commit == "abc123"


def test_parser_evaluate_with_args(parser):
    """Test parsing evaluate command with arguments."""
    args = parser.parse_args(
        [
            "evaluate",
            "--dataset",
            "imagine_la",
            "--k",
            "5",
            "15",
            "--qa-pairs-version",
            "v1",
            "--output-dir",
            "custom/output",
            "--min-score",
            "0.5",
            "--sampling",
            "0.2",
            "--random-seed",
            "42",
            "--commit",
            "def456",
        ]
    )

    assert args.command == "evaluate"
    assert args.dataset == ["imagine_la"]
    assert args.k == [5, 15]
    assert args.qa_pairs_version == "v1"
    assert args.output_dir == Path("custom/output")
    assert args.min_score == 0.5
    assert args.sampling == 0.2
    assert args.random_seed == 42
    assert args.commit == "def456"


def test_dataset_mapping():
    """Test dataset name mapping functionality."""
    # Test known mappings
    assert DATASET_MAPPING["imagine_la"] == "Imagine LA"
    assert DATASET_MAPPING["la_policy"] == "DPSS Policy"

    # Test case insensitivity
    test_datasets = ["imagine_la", "IMAGINE_LA", "Imagine_La"]
    for dataset in test_datasets:
        assert DATASET_MAPPING.get(dataset.lower()) == "Imagine LA"


@patch("src.evaluation.cli.main.run_generation")
def test_main_generate(mock_run_generation, parser):
    """Test main function with generate command."""
    with patch("sys.argv", ["cli.py", "generate", "--dataset", "imagine_la"]):
        main()

        mock_run_generation.assert_called_once()
        args = mock_run_generation.call_args[1]
        assert isinstance(args["config"], GenerationConfig)
        assert args["dataset_filter"] == ["Imagine LA"]


@patch("src.evaluation.cli.main.run_evaluation")
@patch("src.evaluation.cli.main.QAPairStorage")
def test_main_evaluate(mock_storage_class, mock_run_evaluation, parser):
    """Test main function with evaluate command."""
    # Setup mock storage
    mock_storage = MagicMock()
    mock_storage.get_latest_version.return_value = "latest_version"
    mock_storage.get_version_path.return_value = Path("test/path")
    mock_storage_class.return_value = mock_storage

    with patch("sys.argv", ["cli.py", "evaluate", "--dataset", "imagine_la"]):
        main()

        mock_run_evaluation.assert_called_once()
        args = mock_run_evaluation.call_args[1]
        assert args["dataset_filter"] == ["Imagine LA"]
        assert isinstance(args["k_values"], list)
        assert args["min_score"] == -1.0


def test_main_no_command(capsys):
    """Test main function with no command prints help."""
    with patch("sys.argv", ["cli.py"]):
        main()
        captured = capsys.readouterr()
        assert "usage:" in captured.out


@patch("src.evaluation.cli.main.run_generation")
def test_main_generate_no_documents_error(mock_run_generation, parser):
    """Test main function handles 'No documents found' error."""
    mock_run_generation.side_effect = ValueError("No documents found")

    with (
        patch("sys.argv", ["cli.py", "generate", "--dataset", "invalid_dataset"]),
        patch("builtins.print") as mock_print,
    ):
        main()

        # Verify error message was printed
        mock_print.assert_called_with(
            f"No documents found matching criteria. Available datasets: {list(DATASET_MAPPING.keys())}"
        )


@patch("src.evaluation.cli.main.run_evaluation")
@patch("src.evaluation.cli.main.QAPairStorage")
def test_main_evaluate_error(mock_storage_class, mock_run_evaluation, parser):
    """Test main function handles evaluation errors."""
    # Setup mock storage to raise the error
    mock_storage = MagicMock()
    mock_storage.get_latest_version.side_effect = ValueError(
        "No QA pairs found - run generation first"
    )
    mock_storage_class.return_value = mock_storage

    mock_run_evaluation.side_effect = Exception("Test error")  # This won't be reached
    mock_print = MagicMock()

    with (
        patch("sys.argv", ["cli.py", "evaluate"]),
        patch("builtins.print", mock_print),
    ):
        with pytest.raises(ValueError, match="No QA pairs found - run generation first"):
            main()

        # Verify error message was printed
        mock_print.assert_called_with(
            "Error running evaluation: No QA pairs found - run generation first"
        )


@patch("src.evaluation.cli.main.run_evaluation")
@patch("src.evaluation.cli.main.QAPairStorage")
def test_main_evaluate_run_error(mock_storage_class, mock_run_evaluation, parser):
    """Test main function handles run_evaluation errors."""
    # Setup mock storage to work normally
    mock_storage = MagicMock()
    mock_storage.get_latest_version.return_value = "test_version"
    mock_storage_class.return_value = mock_storage

    # Setup run_evaluation to raise error
    mock_run_evaluation.side_effect = Exception("Test error")
    mock_print = MagicMock()

    with (
        patch("sys.argv", ["cli.py", "evaluate"]),
        patch("builtins.print", mock_print),
    ):
        with pytest.raises(Exception, match="Test error"):
            main()

        # Verify error message was printed
        mock_print.assert_called_with("Error running evaluation: Test error")

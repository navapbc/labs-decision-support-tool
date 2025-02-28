"""Tests for the evaluate CLI module."""

import argparse
from pathlib import Path
from unittest import mock

import pytest

from src.evaluation.cli import evaluate


@pytest.fixture
def mock_run_evaluation():
    """Mock the run_evaluation function."""
    with mock.patch("src.evaluation.cli.evaluate.run_evaluation") as mock_run:
        yield mock_run


@pytest.fixture
def mock_create_retrieval_function():
    """Mock the create_retrieval_function."""
    with mock.patch("src.evaluation.cli.evaluate.create_retrieval_function") as mock_func:
        mock_retrieval = mock.MagicMock()
        mock_func.return_value = mock_retrieval
        yield mock_func, mock_retrieval


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


def test_main_with_dataset(mock_run_evaluation, mock_create_retrieval_function):
    """Test the main function with a dataset specified."""
    mock_func, mock_retrieval = mock_create_retrieval_function

    with mock.patch("sys.argv", ["evaluate.py", "--dataset", "imagine_la", "--k", "5", "10"]):
        evaluate.main()

        # Check that run_evaluation was called with the right arguments
        mock_run_evaluation.assert_called_once()
        args, kwargs = mock_run_evaluation.call_args

        assert kwargs["dataset_filter"] == ["Imagine LA"]
        assert kwargs["k_values"] == [5, 10]
        assert kwargs["sample_fraction"] is None
        assert kwargs["random_seed"] is None
        assert kwargs["min_score"] == -1.0
        assert kwargs["retrieval_func"] == mock_retrieval
        assert "log_dir" in kwargs
        assert "commit" in kwargs


def test_main_with_sampling(mock_run_evaluation, mock_create_retrieval_function):
    """Test the main function with sampling specified."""
    mock_func, mock_retrieval = mock_create_retrieval_function

    with mock.patch(
        "sys.argv",
        ["evaluate.py", "--sampling", "0.5", "--random-seed", "42", "--min-score", "0.7"],
    ):
        evaluate.main()

        # Check that run_evaluation was called with the right arguments
        mock_run_evaluation.assert_called_once()
        args, kwargs = mock_run_evaluation.call_args

        assert kwargs["dataset_filter"] is None
        assert kwargs["k_values"] == [5, 10, 25]  # Default values
        assert kwargs["sample_fraction"] == 0.5
        assert kwargs["random_seed"] == 42
        assert kwargs["min_score"] == 0.7
        assert kwargs["retrieval_func"] == mock_retrieval


def test_main_error_handling(mock_run_evaluation):
    """Test error handling in the main function."""
    test_error = RuntimeError("Test error")
    mock_run_evaluation.side_effect = test_error

    with mock.patch("sys.argv", ["evaluate.py"]):
        with mock.patch("builtins.print") as mock_print:
            with pytest.raises(RuntimeError, match="Test error"):
                evaluate.main()

            # Check that the error message was printed
            mock_print.assert_called_with("Error running evaluation: Test error")

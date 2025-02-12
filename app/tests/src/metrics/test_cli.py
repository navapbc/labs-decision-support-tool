"""Tests for metrics CLI module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.metrics.cli import create_retrieval_function, format_metric_value, main, parse_k_values


def test_format_metric_value():
    """Test formatting of different metric value types."""
    # Test float formatting
    assert format_metric_value(0.75) == "0.7500"
    assert format_metric_value(1.0) == "1.0000"

    # Test integer formatting
    assert format_metric_value(5) == "5.0000"
    assert format_metric_value(0) == "0.0000"

    # Test string values
    assert format_metric_value("test") == "test"

    # Test list values
    assert format_metric_value(["a", "b"]) == "['a', 'b']"

    # Test dict values
    assert format_metric_value({"key": "value"}) == "{'key': 'value'}"


def test_parse_k_values():
    """Test parsing of k values from string."""
    # Test single value
    assert parse_k_values("5") == [5]

    # Test multiple values
    assert parse_k_values("5,10,25") == [5, 10, 25]

    # Test invalid input
    with pytest.raises(ValueError):
        parse_k_values("5,abc,25")


def test_create_retrieval_function():
    """Test creation of retrieval function with min_score."""
    min_score = 0.5
    retrieval_func = create_retrieval_function(min_score)

    # Mock the retrieve_with_scores function
    with patch("src.metrics.cli.retrieve_with_scores") as mock_retrieve:
        mock_retrieve.return_value = ["result1", "result2"]

        # Test the created function
        results = retrieval_func("test query", 2)

        # Verify the mock was called with correct parameters
        mock_retrieve.assert_called_once_with("test query", 2, min_score)
        assert results == ["result1", "result2"]


@pytest.mark.parametrize(
    "args,expected_dataset_filter",
    [
        (["--dataset", "imagine_la"], ["imagine_la"]),
        (["--dataset", "all"], None),
    ],
)
def test_main_dataset_filter(args, expected_dataset_filter):
    """Test main function handles dataset filter correctly."""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        # Setup mock arguments
        mock_args.return_value = MagicMock(
            dataset=args[1],
            k="5,10",
            questions_file="test_file.csv",
            sampling=None,
            min_score=-1.0,
            commit="test_commit",
        )

        with patch("src.metrics.cli.run_evaluation") as mock_run_eval:
            with patch("src.metrics.cli.create_retrieval_function") as mock_create_retrieval:
                with patch("os.makedirs"):
                    with patch("os.path.join", return_value="test_path"):
                        with patch("os.listdir", return_value=[]):
                            # Run main function
                            main()

                            # Verify run_evaluation was called with correct dataset_filter
                            call_args = mock_run_eval.call_args[1]
                            assert call_args["dataset_filter"] == expected_dataset_filter

                            # Verify create_retrieval_function was called with correct min_score
                            mock_create_retrieval.assert_called_once_with(-1.0)


@pytest.mark.parametrize("k_value", ["5", "5,10,25"])
def test_main_k_values(k_value):
    """Test main function handles k values correctly."""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        # Setup mock arguments
        mock_args.return_value = MagicMock(
            dataset="all",
            k=k_value,
            questions_file="test_file.csv",
            sampling=None,
            min_score=-1.0,
            commit="test_commit",
        )

        with patch("src.metrics.cli.run_evaluation") as mock_run_eval:
            with patch("src.metrics.cli.create_retrieval_function"):
                with patch("os.makedirs"):
                    with patch("os.path.join", return_value="test_path"):
                        with patch("os.listdir", return_value=[]):
                            # Run main function
                            main()

                            # Verify run_evaluation was called with correct k_values
                            call_args = mock_run_eval.call_args[1]
                            expected_k_values = [int(k) for k in k_value.split(",")]
                            assert call_args["k_values"] == expected_k_values


def test_main_results_display():
    """Test main function displays results correctly."""
    mock_metrics = {
        "batch_id": "test_batch",
        "timestamp": "2024-02-11T12:00:00",
        "commit": "test_commit",
        "overall_metrics": {
            "recall_at_k": 0.75,
            "incorrect_retrievals_analysis": {
                "incorrect_retrievals_count": 10,
                "avg_score_incorrect": 0.45,
                "datasets_with_incorrect_retrievals": ["dataset1"],
            },
        },
        "dataset_metrics": {"dataset1": {"recall_at_k": 0.75, "sample_size": 100}},
    }

    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(
            dataset="all",
            k="5",
            questions_file="test_file.csv",
            sampling=None,
            min_score=-1.0,
            commit="test_commit",
        )

        with patch("src.metrics.cli.run_evaluation"):
            with patch("src.metrics.cli.create_retrieval_function"):
                with patch("os.makedirs"):
                    with patch("os.path.join", return_value="test_path"):
                        with patch("os.listdir", return_value=["metrics_123.json"]):
                            with patch("builtins.open", create=True) as mock_open:
                                # Mock the file read operation to return proper JSON string
                                mock_open.return_value.__enter__.return_value.read.return_value = (
                                    json.dumps(mock_metrics)
                                )

                                # Run main function
                                main()

                                # Verify file was opened
                                mock_open.assert_called()

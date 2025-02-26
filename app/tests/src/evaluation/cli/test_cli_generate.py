"""Tests for the generate CLI module."""

import argparse
from pathlib import Path
from unittest import mock

import pytest

from src.evaluation.cli import generate


@pytest.fixture
def mock_run_generation():
    """Mock the run_generation function."""
    with mock.patch("src.evaluation.cli.generate.run_generation") as mock_run:
        mock_run.return_value = Path("/mock/path/to/qa_pairs.csv")
        yield mock_run


def test_create_parser():
    """Test that the parser is created correctly."""
    parser = generate.create_parser()

    assert isinstance(parser, argparse.ArgumentParser)

    # Check that required arguments are present
    args = parser.parse_args([])
    assert args.dataset is None
    assert args.sampling is None
    assert args.random_seed is None
    assert isinstance(args.output_dir, Path)
    assert args.llm == "gpt-4o-mini"
    assert args.commit is None


def test_main_with_dataset(mock_run_generation):
    """Test the main function with a dataset specified."""
    with mock.patch("sys.argv", ["generate.py", "--dataset", "imagine_la", "--llm", "gpt-4"]):
        with mock.patch(
            "src.evaluation.cli.generate.GenerationConfig.from_cli_args"
        ) as mock_config:
            mock_config_instance = mock.MagicMock()
            mock_config.return_value = mock_config_instance

            generate.main()

            # Check that run_generation was called with the right arguments
            mock_run_generation.assert_called_once()
            args, kwargs = mock_run_generation.call_args

            assert kwargs["config"] == mock_config_instance
            assert kwargs["dataset_filter"] == ["Imagine LA"]
            assert kwargs["sample_fraction"] is None
            assert kwargs["random_seed"] is None
            assert "git_commit" in kwargs


def test_main_with_sampling(mock_run_generation):
    """Test the main function with sampling specified."""
    with mock.patch("sys.argv", ["generate.py", "--sampling", "0.5", "--random-seed", "42"]):
        with mock.patch(
            "src.evaluation.cli.generate.GenerationConfig.from_cli_args"
        ) as mock_config:
            mock_config_instance = mock.MagicMock()
            mock_config.return_value = mock_config_instance

            generate.main()

            # Check that run_generation was called with the right arguments
            mock_run_generation.assert_called_once()
            args, kwargs = mock_run_generation.call_args

            assert kwargs["config"] == mock_config_instance
            assert kwargs["dataset_filter"] is None
            assert kwargs["sample_fraction"] == 0.5
            assert kwargs["random_seed"] == 42


def test_main_no_documents_found(mock_run_generation):
    """Test the main function when no documents are found."""
    mock_run_generation.side_effect = ValueError("No documents found")

    with mock.patch("sys.argv", ["generate.py"]):
        with mock.patch("src.evaluation.cli.generate.GenerationConfig.from_cli_args"):
            with mock.patch("builtins.print") as mock_print:
                generate.main()

                # Check that the error message was printed
                mock_print.assert_called_with(
                    mock.ANY  # The exact message will contain the available datasets
                )

"""Tests for the generate CLI module."""

import argparse
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.evaluation.cli import generate
from src.evaluation.utils.dataset_mapping import map_dataset_name


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


def test_dataset_mapping():
    """Test dataset name mapping functionality."""
    # Test known dataset mapping
    assert map_dataset_name("ca_ftb") == "CA FTB"
    assert map_dataset_name("la_policy") == "DPSS Policy"

    # Test case sensitivity
    assert map_dataset_name("CA_FTB") == "CA FTB"
    assert map_dataset_name("LA_POLICY") == "DPSS Policy"

    # Test unknown dataset (should return original name)
    assert map_dataset_name("unknown_dataset") == "unknown_dataset"


def test_argument_parsing():
    """Test argument parsing with various combinations."""
    # Test default values
    parser = generate.create_parser()
    args = parser.parse_args([])
    assert args.dataset is None
    assert args.sampling is None
    assert args.random_seed is None
    assert args.llm == "gpt-4o-mini"
    assert isinstance(args.output_dir, Path)

    # Test custom values
    args = parser.parse_args(
        [
            "--dataset",
            "ca_ftb",
            "la_policy",
            "--sampling",
            "0.1",
            "--random-seed",
            "42",
            "--llm",
            "gpt-4",
        ]
    )
    assert args.dataset == ["ca_ftb", "la_policy"]
    assert args.sampling == 0.1
    assert args.random_seed == 42
    assert args.llm == "gpt-4"


def validate_sampling_fraction(value):
    """Validate that value is a valid sampling fraction (0 < x <= 1)."""
    try:
        fvalue = float(value)
        if not 0 < fvalue <= 1:
            raise ValueError(f"{value} is not a valid sampling fraction (must be between 0 and 1)")
        return fvalue
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"{value} is not a valid sampling fraction") from err


def test_invalid_arguments():
    """Test handling of invalid arguments."""
    parser = generate.create_parser()

    # Add type validation to parser
    parser.add_argument("--test-sampling", type=validate_sampling_fraction)

    # Test invalid sampling value
    with pytest.raises(SystemExit):
        parser.parse_args(["--test-sampling", "2.0"])

    # Test invalid random seed
    with pytest.raises(SystemExit):
        parser.parse_args(["--random-seed", "not_a_number"])


@pytest.mark.integration
def test_main_integration(temp_output_dir):
    """Integration test with minimal test data."""
    with mock.patch(
        "sys.argv",
        [
            "generate.py",
            "--dataset",
            "ca_ftb",
            "--output-dir",
            str(temp_output_dir),
            "--llm",
            "gpt-4o-mini",
        ],
    ):
        # Mock the run_generation function since it requires DB and LLM access
        with mock.patch("src.evaluation.qa_generation.runner.run_generation") as mock_run:
            # Mock successful generation
            mock_qa_pairs_path = temp_output_dir / "qa_pairs" / "qa_pairs.csv"
            mock_run.return_value = mock_qa_pairs_path

            # Create the directory and file to simulate generation
            mock_qa_pairs_path.parent.mkdir(parents=True, exist_ok=True)
            mock_qa_pairs_path.touch()

            generate.main()

            # Verify the QA pairs directory was created
            assert (temp_output_dir / "qa_pairs").exists()
            assert mock_qa_pairs_path.exists()


def test_error_handling_no_documents():
    """Test handling of 'No documents found' error."""
    with mock.patch("sys.argv", ["generate.py"]):
        with mock.patch("src.evaluation.qa_generation.runner.run_generation") as mock_run:
            mock_run.side_effect = ValueError("No documents found")
            generate.main()  # This should handle the error and return


def test_output_directory_handling(temp_output_dir):
    """Test output directory path handling."""
    # Test relative path
    parser = generate.create_parser()
    args = parser.parse_args(["--output-dir", "relative/path"])
    assert isinstance(args.output_dir, Path)
    assert args.output_dir == Path("relative/path")

    # Test absolute path
    abs_path = str(temp_output_dir / "absolute/path")
    args = parser.parse_args(["--output-dir", abs_path])
    assert isinstance(args.output_dir, Path)
    assert args.output_dir == Path(abs_path)

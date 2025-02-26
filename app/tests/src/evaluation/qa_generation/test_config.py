"""Tests for QA generation configuration."""

from argparse import Namespace
from pathlib import Path

import pytest

from src.evaluation.qa_generation.config import GenerationConfig, QuestionSource


@pytest.fixture
def mock_args():
    """Create mock CLI arguments."""
    return Namespace(
        llm="test-model",
        output_dir=Path("test/output"),
        dataset=["test_dataset"],
        sampling=0.5,
        random_seed=42,
    )


def test_generation_config_defaults():
    """Test GenerationConfig default values."""
    config = GenerationConfig()
    assert config.llm_model == "gpt-4o-mini"
    assert config.output_dir == GenerationConfig.DEFAULT_OUTPUT_DIR
    assert config.dataset_filter is None
    assert config.sample_fraction is None
    assert config.random_seed is None
    assert config.question_source == QuestionSource.CHUNK


def test_generation_config_custom_values():
    """Test GenerationConfig with custom values."""
    config = GenerationConfig(
        llm_model="test-model",
        output_dir=Path("custom/path"),
        dataset_filter=["test_dataset"],
        sample_fraction=0.5,
        random_seed=42,
        question_source=QuestionSource.DOCUMENT,
    )

    assert config.llm_model == "test-model"
    assert config.output_dir == Path("custom/path")
    assert config.dataset_filter == ["test_dataset"]
    assert config.sample_fraction == 0.5
    assert config.random_seed == 42
    assert config.question_source == QuestionSource.DOCUMENT


def test_generation_config_from_cli_args(mock_args):
    """Test creating config from CLI arguments."""
    config = GenerationConfig.from_cli_args(mock_args)

    assert config.llm_model == "test-model"
    assert config.output_dir == Path("test/output")
    assert config.dataset_filter == ["test_dataset"]
    assert config.sample_fraction == 0.5
    assert config.random_seed == 42


def test_qa_pairs_dir():
    """Test qa_pairs_dir property."""
    config = GenerationConfig(output_dir=Path("test/output"))
    qa_pairs_dir = config.qa_pairs_dir

    assert qa_pairs_dir.parent.name == "qa_pairs"
    assert qa_pairs_dir.parent.parent == Path("test/output")
    # Version ID should be in format YYYYMMDD_HHMMSS
    assert len(qa_pairs_dir.name) == 15
    assert qa_pairs_dir.name[:8].isdigit()
    assert qa_pairs_dir.name[8] == "_"
    assert qa_pairs_dir.name[9:].isdigit()


def test_latest_symlink():
    """Test latest_symlink property."""
    config = GenerationConfig(output_dir=Path("test/output"))
    latest_link = config.latest_symlink

    assert latest_link.name == "latest"
    assert latest_link.parent.name == "qa_pairs"
    assert latest_link.parent.parent == Path("test/output")

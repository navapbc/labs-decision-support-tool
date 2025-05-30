"""Tests for evaluation logging functionality."""

import json
import os

import pytest

from src.evaluation.data_models import (
    BatchConfig,
    DatasetMetrics,
    EvaluationConfig,
    EvaluationResult,
    ExpectedChunk,
    IncorrectRetrievalsAnalysis,
    MetricsSummary,
    RetrievedChunk,
    SoftwareInfo,
)
from src.evaluation.metrics.logging import EvaluationLogger


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for logs."""
    log_dir = tmp_path / "test_logs"
    log_dir.mkdir()
    return str(log_dir)


@pytest.fixture
def test_batch_config():
    """Create a test batch configuration."""
    eval_config = EvaluationConfig(
        k_value=5,
        num_samples=10,
        dataset_filter=["test_dataset"],
    )
    software_info = SoftwareInfo(
        package_version="1.0.0",
        git_commit="test123",
    )
    return BatchConfig(
        evaluation_config=eval_config,
        software_info=software_info,
    )


@pytest.fixture
def test_evaluation_result():
    """Create a test evaluation result."""
    expected = ExpectedChunk(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
        content="test content",
        document_id="doc456",
    )

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id="chunk123",
            score=0.85,
            content="test content",
            content_hash="hash456",
            document_id="doc456",
        )
    ]

    return EvaluationResult(
        qa_pair_id="qa123",
        question="test question?",
        expected_answer="test answer",
        expected_chunk=expected,
        retrieved_chunks=retrieved_chunks,
        correct_chunk_retrieved=True,
        rank_if_found=1,
        retrieval_time_ms=100.5,
        timestamp="2024-01-01T00:00:00Z",
        correct_document_retrieved=True,
        document_rank_if_found=1,
        dataset="test_dataset",
    )


@pytest.fixture
def test_metrics_summary():
    """Create a test metrics summary."""
    dataset_metrics = {
        "test_dataset": DatasetMetrics(
            recall_at_k=0.75,
            sample_size=10,
            avg_score_incorrect=0.45,
            document_recall_at_k=0.85,
        )
    }

    incorrect_analysis = IncorrectRetrievalsAnalysis(
        incorrect_retrievals_count=2,
        avg_score_incorrect=0.45,
        datasets_with_incorrect_retrievals=["test_dataset"],
    )

    return MetricsSummary(
        batch_id="test_batch",
        timestamp="2024-01-01T00:00:00Z",
        overall_metrics={
            "recall_at_k": 0.75,
            "document_recall_at_k": 0.85,
            "mean_retrieval_time_ms": 100.5,
            "total_questions": 10,
            "successful_retrievals": 8,
            "successful_document_retrievals": 9,
        },
        dataset_metrics=dataset_metrics,
        incorrect_analysis=incorrect_analysis,
    )


def test_logger_initialization(temp_log_dir):
    """Test logger initialization and directory creation."""
    logger = EvaluationLogger(temp_log_dir)
    assert os.path.exists(logger.log_dir)
    assert logger.batch_id is None
    assert logger.results_file is None


def test_start_batch(temp_log_dir, test_batch_config):
    """Test starting a new evaluation batch."""
    logger = EvaluationLogger(temp_log_dir)
    logger.start_batch(test_batch_config)

    # Check that batch ID is set
    assert logger.batch_id == test_batch_config.batch_id

    # Check that config file was created
    config_file = os.path.join(logger.log_dir, f"batch_{logger.batch_id}.json")
    assert os.path.exists(config_file)

    # Check config file contents
    with open(config_file) as f:
        config_data = json.load(f)
        assert config_data["batch_id"] == test_batch_config.batch_id
        assert (
            config_data["evaluation_config"]["k_value"]
            == test_batch_config.evaluation_config.k_value
        )
        assert (
            config_data["evaluation_config"]["num_samples"]
            == test_batch_config.evaluation_config.num_samples
        )
        assert (
            config_data["evaluation_config"]["dataset_filter"]
            == test_batch_config.evaluation_config.dataset_filter
        )
        assert (
            config_data["software_info"]["package_version"]
            == test_batch_config.software_info.package_version
        )
        assert (
            config_data["software_info"]["git_commit"] == test_batch_config.software_info.git_commit
        )

    # Check that results file was created
    results_file = os.path.join(logger.log_dir, f"results_{logger.batch_id}.jsonl")
    assert os.path.exists(results_file)


def test_log_result(temp_log_dir, test_batch_config, test_evaluation_result):
    """Test logging individual evaluation results."""
    logger = EvaluationLogger(temp_log_dir)
    logger.start_batch(test_batch_config)

    # Log a result
    logger.log_result(test_evaluation_result)

    # Read the results file
    results_file = os.path.join(logger.log_dir, f"results_{logger.batch_id}.jsonl")
    with open(results_file) as f:
        result_data = json.loads(f.readline().strip())
        assert result_data["qa_pair_id"] == test_evaluation_result.qa_pair_id
        assert result_data["question"] == test_evaluation_result.question


def test_finish_batch(temp_log_dir, test_batch_config, test_metrics_summary):
    """Test finishing a batch and writing summary metrics."""
    logger = EvaluationLogger(temp_log_dir)
    logger.start_batch(test_batch_config)

    # Finish the batch
    logger.finish_batch(test_metrics_summary)

    # Check that metrics file was created
    metrics_file = os.path.join(logger.log_dir, f"metrics_{logger.batch_id}.json")
    assert os.path.exists(metrics_file)

    # Check metrics file contents
    with open(metrics_file) as f:
        metrics_data = json.load(f)
        assert metrics_data["batch_id"] == test_metrics_summary.batch_id
        assert metrics_data["overall_metrics"]["recall_at_k"] == 0.75
        assert len(metrics_data["dataset_metrics"]) == 1


def test_context_manager(temp_log_dir):
    """Test using logger as a context manager."""
    with EvaluationLogger(temp_log_dir) as logger:
        assert logger.log_dir is not None
        assert logger.batch_id is None
        assert logger.results_file is None

    # After exiting context, results file should be closed
    assert logger.results_file is None


def test_context_manager_error_handling(temp_log_dir, test_batch_config):
    """Test that files are cleaned up when an error occurs."""
    logger = None
    try:
        with EvaluationLogger(temp_log_dir) as logger:
            # Start a batch to create some files
            logger.start_batch(test_batch_config)

            # Verify files were created
            config_file = os.path.join(logger.log_dir, f"batch_{logger.batch_id}.json")
            results_file = os.path.join(logger.log_dir, f"results_{logger.batch_id}.jsonl")
            assert os.path.exists(config_file)
            assert os.path.exists(results_file)

            # Simulate an error
            raise ValueError("Test error")

    except ValueError:
        # Verify files were cleaned up
        if logger and logger.batch_id:
            config_file = os.path.join(logger.log_dir, f"batch_{logger.batch_id}.json")
            results_file = os.path.join(logger.log_dir, f"results_{logger.batch_id}.jsonl")
            assert not os.path.exists(config_file)
            assert not os.path.exists(results_file)


def test_context_manager_success_case(temp_log_dir, test_batch_config, test_metrics_summary):
    """Test that files are preserved when no error occurs."""
    with EvaluationLogger(temp_log_dir) as logger:
        # Start a batch and finish it normally
        logger.start_batch(test_batch_config)
        logger.finish_batch(test_metrics_summary)

        # Remember the files we created
        config_file = os.path.join(logger.log_dir, f"batch_{logger.batch_id}.json")
        results_file = os.path.join(logger.log_dir, f"results_{logger.batch_id}.jsonl")
        metrics_file = os.path.join(logger.log_dir, f"metrics_{logger.batch_id}.json")

    # After context exit, files should still exist
    assert os.path.exists(config_file)
    assert os.path.exists(results_file)
    assert os.path.exists(metrics_file)

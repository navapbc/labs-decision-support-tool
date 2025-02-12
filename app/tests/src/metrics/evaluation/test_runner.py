"""Tests for evaluation runner."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.metrics.evaluation.runner import EvaluationRunner, run_evaluation


@pytest.fixture
def mock_retrieval_func():
    """Create a mock retrieval function."""
    return MagicMock()


@pytest.fixture
def mock_questions():
    """Create mock questions data."""
    return [
        {
            "id": "1",
            "question": "test question 1?",
            "answer": "test answer 1",
            "dataset": "dataset1",
        },
        {
            "id": "2",
            "question": "test question 2?",
            "answer": "test answer 2",
            "dataset": "dataset2",
        },
    ]


def test_evaluation_runner_init(mock_retrieval_func):
    """Test EvaluationRunner initialization."""
    runner = EvaluationRunner(mock_retrieval_func)
    assert runner.retrieval_func == mock_retrieval_func
    assert runner.log_dir == "logs/evaluations"


def test_load_questions_success(mock_questions):
    """Test successful loading of questions from CSV."""
    runner = EvaluationRunner(MagicMock())

    # Mock CSV file content
    csv_content = "id,question,answer,dataset\n1,test question 1?,test answer 1,dataset1\n2,test question 2?,test answer 2,dataset2"

    with patch("builtins.open", mock_open(read_data=csv_content)):
        questions = runner.load_questions("test.csv")

        assert len(questions) == 2
        assert questions[0]["id"] == "1"
        assert questions[0]["question"] == "test question 1?"
        assert questions[0]["dataset"] == "dataset1"


def test_load_questions_file_not_found():
    """Test loading questions from non-existent file."""
    runner = EvaluationRunner(MagicMock())

    with pytest.raises(RuntimeError, match="Error loading questions"):
        runner.load_questions("nonexistent.csv")


def test_run_evaluation_batch(mock_retrieval_func, mock_questions):
    """Test running a single evaluation batch."""
    runner = EvaluationRunner(mock_retrieval_func)

    # Mock dependencies
    with patch("src.metrics.evaluation.runner.create_batch_config") as mock_create_config:
        with patch("src.metrics.evaluation.runner.EvaluationLogger") as mock_logger_cls:
            with patch("src.metrics.evaluation.runner.batch_process_results") as mock_process:
                with patch("src.metrics.evaluation.runner.compute_metrics_summary") as mock_compute:
                    # Setup mocks
                    mock_config = MagicMock()
                    mock_create_config.return_value = mock_config
                    mock_logger = MagicMock()
                    mock_logger_cls.return_value = mock_logger
                    mock_process.return_value = ["result1", "result2"]
                    mock_compute.return_value = {"metric1": 0.5}

                    # Run batch
                    runner.run_evaluation_batch(mock_questions, k=5)

                    # Verify mocks were called correctly
                    mock_create_config.assert_called_once_with(k_value=5, dataset_filter=None)
                    mock_logger_cls.assert_called_once_with(runner.log_dir)
                    mock_logger.start_batch.assert_called_once_with(mock_config)
                    mock_process.assert_called_once_with(mock_questions, mock_retrieval_func, 5)
                    mock_compute.assert_called_once()
                    mock_logger.finish_batch.assert_called_once()


def test_run_evaluation_with_filtering(mock_retrieval_func, mock_questions):
    """Test running evaluation with dataset filtering."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=mock_questions):
        with patch.object(runner, "run_evaluation_batch") as mock_run_batch:
            # Run evaluation with dataset filter
            runner.run_evaluation(
                questions_file="test.csv", k_values=[5], dataset_filter=["dataset1"]
            )

            # Verify filtered questions were passed to batch
            call_args = mock_run_batch.call_args[0]
            filtered_questions = call_args[0]
            assert len(filtered_questions) == 1
            assert filtered_questions[0]["dataset"] == "dataset1"


def test_run_evaluation_with_sampling(mock_retrieval_func, mock_questions):
    """Test running evaluation with sampling."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=mock_questions):
        with patch.object(runner, "run_evaluation_batch") as mock_run_batch:
            with patch("src.metrics.evaluation.runner.stratified_sample") as mock_sample:
                # Setup mock sampler
                mock_sample.return_value = [mock_questions[0]]

                # Run evaluation with sampling
                runner.run_evaluation(questions_file="test.csv", k_values=[5], sample_fraction=0.5)

                # Verify sampled questions were passed to batch
                mock_sample.assert_called_once_with(
                    mock_questions, sample_fraction=0.5, min_per_dataset=1, random_seed=None
                )
                call_args = mock_run_batch.call_args[0]
                sampled_questions = call_args[0]
                assert len(sampled_questions) == 1


def test_run_evaluation_no_questions(mock_retrieval_func):
    """Test running evaluation with no questions after filtering."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=[]):
        with pytest.raises(ValueError, match="No questions to evaluate"):
            runner.run_evaluation(questions_file="test.csv", k_values=[5])


def test_run_evaluation_batch_error_handling(mock_retrieval_func, mock_questions):
    """Test error handling in evaluation batch."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch("src.metrics.evaluation.runner.create_batch_config"):
        with patch("src.metrics.evaluation.runner.EvaluationLogger") as mock_logger_cls:
            mock_logger = MagicMock()
            mock_logger_cls.return_value = mock_logger

            # Simulate an error in batch processing
            with patch(
                "src.metrics.evaluation.runner.batch_process_results",
                side_effect=Exception("Test error"),
            ):
                with pytest.raises(Exception, match="Test error"):
                    runner.run_evaluation_batch(mock_questions, k=5)

                # Verify logger cleanup was called
                mock_logger.__exit__.assert_called_once()


def test_convenience_function(mock_retrieval_func):
    """Test the convenience function run_evaluation."""
    with patch("src.metrics.evaluation.runner.EvaluationRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        # Call convenience function
        run_evaluation(
            questions_file="test.csv",
            k_values=[5],
            retrieval_func=mock_retrieval_func,
            dataset_filter=["dataset1"],
            sample_fraction=0.5,
            min_score=None,
            random_seed=None,
            log_dir="test_logs",
        )

        # Verify runner was created and called correctly
        mock_runner_cls.assert_called_once_with(
            retrieval_func=mock_retrieval_func, log_dir="test_logs"
        )
        mock_runner.run_evaluation.assert_called_once_with(
            questions_file="test.csv",
            k_values=[5],
            dataset_filter=["dataset1"],
            min_score=None,
            sample_fraction=0.5,
            random_seed=None,
        )

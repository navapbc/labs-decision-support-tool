"""Tests for metrics evaluation runner functionality."""

from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.metrics.runner import EvaluationRunner, run_evaluation


@pytest.fixture
def mock_retrieval_func():
    """Create a mock retrieval function."""
    return MagicMock()


@pytest.fixture
def mock_questions():
    """Create mock questions for testing."""
    return [
        {
            "id": "test1",
            "question": "Test question 1?",
            "answer": "Test answer 1",
            "document_id": "doc1",
            "dataset": "test_dataset",
        },
        {
            "id": "test2",
            "question": "Test question 2?",
            "answer": "Test answer 2",
            "document_id": "doc2",
            "dataset": "test_dataset",
        },
    ]


@pytest.fixture
def mock_qa_metadata():
    """Create mock QA metadata."""
    return {
        "version_id": "test_version",
        "timestamp": "2024-02-20T00:00:00",
        "llm_model": "test-model",
        "total_pairs": 10,
        "datasets": ["test_dataset"],
        "git_commit": "test_commit",
    }


def test_run_evaluation_basic(mock_retrieval_func, mock_questions, tmp_path):
    """Test basic evaluation run."""
    runner = EvaluationRunner(retrieval_func=mock_retrieval_func)
    questions_file = str(tmp_path / "test.csv")

    with (
        patch.object(runner, "load_questions", return_value=mock_questions),
        patch.object(runner, "run_evaluation_batch") as mock_run_batch,
    ):
        # Run evaluation
        runner.run_evaluation(questions_file=questions_file, k_values=[5])

        # Verify batch was run with all questions
        mock_run_batch.assert_called_once()
        call_args = mock_run_batch.call_args[0]
        assert len(call_args[0]) == len(mock_questions)  # First arg is questions
        assert call_args[1] == 5  # Second arg is k value
        assert call_args[2] == questions_file  # Third arg is qa_pairs_file


def test_run_evaluation_with_dataset_filter(mock_retrieval_func, mock_questions):
    """Test evaluation with dataset filtering."""
    runner = EvaluationRunner(retrieval_func=mock_retrieval_func)

    # Add another dataset
    mock_questions.append(
        {
            "id": "test3",
            "question": "Test question 3?",
            "answer": "Test answer 3",
            "document_id": "doc3",
            "dataset": "other_dataset",
        }
    )

    with (
        patch.object(runner, "load_questions", return_value=mock_questions),
        patch.object(runner, "run_evaluation_batch") as mock_run_batch,
    ):
        # Run evaluation with dataset filter
        runner.run_evaluation(
            questions_file="test.csv", k_values=[5], dataset_filter=["test_dataset"]
        )

        # Verify only questions from filtered dataset were used
        mock_run_batch.assert_called_once()
        call_args = mock_run_batch.call_args[0]
        filtered_questions = call_args[0]
        assert len(filtered_questions) == 2
        assert all(q["dataset"] == "test_dataset" for q in filtered_questions)


def test_run_evaluation_with_sampling(mock_retrieval_func, mock_questions):
    """Test running evaluation with sampling."""
    runner = EvaluationRunner(mock_retrieval_func)

    with (
        patch.object(runner, "load_questions", return_value=mock_questions),
        patch.object(runner, "run_evaluation_batch") as mock_run_batch,
        patch("src.evaluation.metrics.runner.stratified_sample") as mock_sample,
    ):
        # Setup mock sampler
        mock_sample.return_value = [mock_questions[0]]

        # Run evaluation with sampling
        runner.run_evaluation(questions_file="test.csv", k_values=[5], sample_fraction=0.5)

        # Verify sampled questions were passed to batch
        mock_sample.assert_called_once_with(mock_questions, sample_fraction=0.5, random_seed=None)
        call_args = mock_run_batch.call_args[0]
        sampled_questions = call_args[0]
        assert len(sampled_questions) == 1


def test_run_evaluation_batch_basic(
    mock_retrieval_func, mock_questions, mock_qa_metadata, tmp_path
):
    """Test basic evaluation batch run."""
    runner = EvaluationRunner(retrieval_func=mock_retrieval_func)
    k = 5
    qa_pairs_file = str(tmp_path / "test.csv")

    # Setup mock retrieval results
    mock_retrieval_func.return_value = [
        {"document_id": "doc1", "score": 0.9},
        {"document_id": "doc2", "score": 0.8},
    ]

    with (
        patch("src.evaluation.metrics.batch.get_git_commit", return_value="test_commit"),
        patch(
            "src.evaluation.utils.storage.QAPairStorage.get_version_metadata",
            return_value=mock_qa_metadata,
        ),
    ):
        # Run batch evaluation
        runner.run_evaluation_batch(mock_questions, k, qa_pairs_file)

        # Verify all questions were attempted
        assert mock_retrieval_func.call_count == len(mock_questions)


def test_run_evaluation_batch_with_errors(
    mock_retrieval_func, mock_questions, mock_qa_metadata, tmp_path
):
    """Test evaluation batch handles retrieval errors."""
    runner = EvaluationRunner(retrieval_func=mock_retrieval_func)
    qa_pairs_file = str(tmp_path / "test.csv")

    # Make retrieval fail for one question
    def mock_retrieve(question, k):
        # Find the original question dict from mock_questions
        question_dict = next((q for q in mock_questions if q["question"] == question), None)
        if question_dict and question_dict["id"] == "test1":
            raise Exception("Retrieval error")
        return [{"document_id": "doc2", "score": 0.8}]

    mock_retrieval_func.side_effect = mock_retrieve

    with (
        patch("src.evaluation.metrics.batch.get_git_commit", return_value="test_commit"),
        patch(
            "src.evaluation.utils.storage.QAPairStorage.get_version_metadata",
            return_value=mock_qa_metadata,
        ),
    ):
        # Run batch evaluation - should raise the error
        with pytest.raises(Exception, match="Retrieval error"):
            runner.run_evaluation_batch(mock_questions, 5, qa_pairs_file)

        # Verify first question was attempted before error
        assert mock_retrieval_func.call_count == 1


def test_run_evaluation_batch_empty_results(
    mock_retrieval_func, mock_questions, mock_qa_metadata, tmp_path
):
    """Test evaluation batch handles empty retrieval results."""
    runner = EvaluationRunner(retrieval_func=mock_retrieval_func)
    qa_pairs_file = str(tmp_path / "test.csv")

    # Return empty results
    mock_retrieval_func.return_value = []

    with (
        patch("src.evaluation.metrics.batch.get_git_commit", return_value="test_commit"),
        patch(
            "src.evaluation.utils.storage.QAPairStorage.get_version_metadata",
            return_value=mock_qa_metadata,
        ),
    ):
        # Run batch evaluation
        runner.run_evaluation_batch(mock_questions, 5, qa_pairs_file)

        # Verify all questions were attempted
        assert mock_retrieval_func.call_count == len(mock_questions)


def test_run_evaluation_cli_integration(mock_retrieval_func, tmp_path):
    """Test CLI integration function."""
    questions_file = tmp_path / "questions.csv"
    log_dir = tmp_path / "logs"

    with patch("src.evaluation.metrics.runner.EvaluationRunner") as MockRunner:
        # Setup mock runner
        mock_runner = MockRunner.return_value
        mock_runner.run_evaluation.return_value = {"metrics": {"recall@5": 0.5}}

        # Run evaluation through CLI function
        run_evaluation(
            questions_file=str(questions_file),
            k_values=[5],
            dataset_filter=["test_dataset"],
            sample_fraction=0.1,
            random_seed=42,
            retrieval_func=mock_retrieval_func,
            log_dir=str(log_dir),
        )

        # Verify runner was called with correct parameters
        MockRunner.assert_called_once_with(
            retrieval_func=mock_retrieval_func,
            log_dir=str(log_dir),
            progress_tracker=None,
        )
        mock_runner.run_evaluation.assert_called_once_with(
            questions_file=str(questions_file),
            k_values=[5],
            dataset_filter=["test_dataset"],
            min_score=None,
            sample_fraction=0.1,
            random_seed=42,
            commit=None,
        )


def test_load_questions_file_not_found(mock_retrieval_func, tmp_path):
    """Test load_questions handles missing file."""
    nonexistent_file = tmp_path / "nonexistent.csv"
    runner = EvaluationRunner(mock_retrieval_func)
    with pytest.raises(RuntimeError, match="Error loading questions"):
        runner.load_questions(str(nonexistent_file))


def test_load_questions_invalid_csv(mock_retrieval_func, tmp_path):
    """Test load_questions handles invalid CSV format."""
    # Create invalid CSV file
    questions_file = tmp_path / "invalid.csv"
    questions_file.write_text("This is not a CSV file at all")  # Not even CSV format

    runner = EvaluationRunner(mock_retrieval_func)
    with pytest.raises(RuntimeError, match="Error loading questions"):
        runner.load_questions(str(questions_file))


def test_run_evaluation_empty_k_values(mock_retrieval_func, mock_questions):
    """Test run_evaluation handles empty k_values list."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=mock_questions):
        # Should complete without running any batches
        runner.run_evaluation(questions_file="test.csv", k_values=[])


def test_run_evaluation_invalid_sample_fraction(mock_retrieval_func, mock_questions):
    """Test run_evaluation handles invalid sample fraction."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=mock_questions):
        with pytest.raises(ValueError):
            runner.run_evaluation(
                questions_file="test.csv", k_values=[5], sample_fraction=2.0  # Invalid: > 1.0
            )


def test_run_evaluation_all_filtered_out(mock_retrieval_func, mock_questions):
    """Test run_evaluation handles case where all questions are filtered out."""
    runner = EvaluationRunner(mock_retrieval_func)

    with patch.object(runner, "load_questions", return_value=mock_questions):
        with pytest.raises(ValueError, match="No questions to evaluate"):
            runner.run_evaluation(
                questions_file="test.csv", k_values=[5], dataset_filter=["nonexistent_dataset"]
            )


def test_run_evaluation_empty_questions(mock_retrieval_func, tmp_path):
    """Test run_evaluation handles empty questions list."""
    # Create empty CSV file with headers
    questions_file = tmp_path / "empty.csv"
    questions_file.write_text("id,question,answer,document_id,dataset\n")

    runner = EvaluationRunner(mock_retrieval_func)
    with pytest.raises(ValueError, match="No questions to evaluate"):
        runner.run_evaluation(questions_file=str(questions_file), k_values=[5])

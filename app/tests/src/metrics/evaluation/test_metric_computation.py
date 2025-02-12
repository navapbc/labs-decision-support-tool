"""Tests for metrics computation functions."""

from src.metrics.evaluation.metric_computation import (
    compute_dataset_metrics,
    compute_incorrect_analysis,
    compute_metrics_summary,
)
from src.metrics.models.metrics import EvaluationResult, ExpectedChunk, RetrievedChunk


def create_test_result(
    correct: bool = True,
    rank: int = 1,
    scores: list = None,
    source: str = "test_dataset",
) -> EvaluationResult:
    """Helper function to create test evaluation results."""
    if scores is None:
        scores = [0.85, 0.75]

    expected = ExpectedChunk(
        name="test_doc",
        source=source,
        chunk_id="chunk123",
        content_hash="hash456",
    )

    retrieved_chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=scores[0],
        content="test content",
    )

    return EvaluationResult(
        qa_pair_id="qa123",
        question="test question?",
        expected_answer="test answer",
        expected_chunk=expected,
        correct_chunk_retrieved=correct,
        rank_if_found=rank if correct else None,
        top_k_scores=scores,
        retrieval_time_ms=100.5,
        retrieved_chunks=[retrieved_chunk],
    )


def test_compute_dataset_metrics():
    """Test dataset metrics computation."""
    # Test with empty results
    empty_metrics = compute_dataset_metrics([])
    assert empty_metrics.recall_at_k == 0.0
    assert empty_metrics.sample_size == 0
    assert empty_metrics.avg_score_incorrect == 0.0

    # Test with all correct results
    correct_results = [create_test_result(correct=True) for _ in range(3)]
    correct_metrics = compute_dataset_metrics(correct_results)
    assert correct_metrics.recall_at_k == 1.0
    assert correct_metrics.sample_size == 3
    assert correct_metrics.avg_score_incorrect == 0.0

    # Test with mixed results
    mixed_results = [
        create_test_result(correct=True, scores=[0.9, 0.8]),
        create_test_result(correct=False, scores=[0.7, 0.6]),
        create_test_result(correct=False, scores=[0.5, 0.4]),
    ]
    mixed_metrics = compute_dataset_metrics(mixed_results)
    assert mixed_metrics.recall_at_k == 1 / 3
    assert mixed_metrics.sample_size == 3
    assert mixed_metrics.avg_score_incorrect == 0.6  # Average of [0.7, 0.5]


def test_compute_incorrect_analysis():
    """Test incorrect retrievals analysis computation."""
    # Test with no incorrect results
    correct_results = [create_test_result(correct=True) for _ in range(3)]
    correct_analysis = compute_incorrect_analysis(correct_results)
    assert correct_analysis.incorrect_retrievals_count == 0
    assert correct_analysis.avg_score_incorrect == 0.0
    assert correct_analysis.datasets_with_incorrect_retrievals == []

    # Test with all incorrect results
    incorrect_results = [
        create_test_result(correct=False, scores=[0.7, 0.6], source="dataset1"),
        create_test_result(correct=False, scores=[0.5, 0.4], source="dataset2"),
        create_test_result(correct=False, scores=[0.3, 0.2], source="dataset1"),
    ]
    incorrect_analysis = compute_incorrect_analysis(incorrect_results)
    assert incorrect_analysis.incorrect_retrievals_count == 3
    assert incorrect_analysis.avg_score_incorrect == 0.5  # Average of [0.7, 0.5, 0.3]
    assert incorrect_analysis.datasets_with_incorrect_retrievals == ["dataset1", "dataset2"]

    # Test sorting of datasets by frequency
    more_results = [
        create_test_result(correct=False, scores=[0.7], source="dataset2"),
        create_test_result(correct=False, scores=[0.6], source="dataset1"),
        create_test_result(correct=False, scores=[0.5], source="dataset2"),
    ]
    freq_analysis = compute_incorrect_analysis(more_results)
    # dataset2 should be first as it has more incorrect retrievals
    assert freq_analysis.datasets_with_incorrect_retrievals == ["dataset2", "dataset1"]


def test_compute_metrics_summary():
    """Test metrics summary computation."""
    results = [
        # Dataset 1 results
        create_test_result(correct=True, scores=[0.9, 0.8], source="dataset1"),
        create_test_result(correct=False, scores=[0.7, 0.6], source="dataset1"),
        # Dataset 2 results
        create_test_result(correct=True, scores=[0.85, 0.75], source="dataset2"),
        create_test_result(correct=False, scores=[0.65, 0.55], source="dataset2"),
    ]

    summary = compute_metrics_summary(results, "batch123")

    # Check basic fields
    assert summary.batch_id == "batch123"
    assert summary.timestamp is not None

    # Check overall metrics
    assert summary.overall_metrics["recall_at_k"] == 0.5  # 2 correct out of 4
    assert summary.overall_metrics["total_questions"] == 4
    assert summary.overall_metrics["successful_retrievals"] == 2
    assert isinstance(summary.overall_metrics["mean_retrieval_time_ms"], float)

    # Check dataset metrics
    assert len(summary.dataset_metrics) == 2
    assert summary.dataset_metrics["dataset1"].recall_at_k == 0.5  # 1 correct out of 2
    assert summary.dataset_metrics["dataset2"].recall_at_k == 0.5  # 1 correct out of 2

    # Check incorrect analysis
    assert summary.incorrect_analysis.incorrect_retrievals_count == 2
    assert len(summary.incorrect_analysis.datasets_with_incorrect_retrievals) == 2
    assert isinstance(summary.incorrect_analysis.avg_score_incorrect, float)

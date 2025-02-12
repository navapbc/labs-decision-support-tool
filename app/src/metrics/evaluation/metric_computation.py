"""Metrics computation for evaluation results."""

from collections import defaultdict
from typing import Dict, List

import numpy as np

from ..models.metrics import (
    DatasetMetrics,
    EvaluationResult,
    IncorrectRetrievalsAnalysis,
    MetricsSummary,
)


def compute_dataset_metrics(results: List[EvaluationResult]) -> DatasetMetrics:
    """Compute metrics for a specific dataset."""
    if not results:
        return DatasetMetrics(recall_at_k=0.0, sample_size=0, avg_score_incorrect=0.0)

    total = len(results)
    correct = sum(1 for r in results if r.correct_chunk_retrieved)

    # Compute average score for incorrect retrievals
    incorrect_results = [r for r in results if not r.correct_chunk_retrieved]
    incorrect_scores = [max(r.top_k_scores) for r in incorrect_results if r.top_k_scores]
    avg_score_incorrect = float(np.mean(incorrect_scores)) if incorrect_scores else 0.0

    return DatasetMetrics(
        recall_at_k=correct / total, sample_size=total, avg_score_incorrect=avg_score_incorrect
    )


def compute_incorrect_analysis(results: List[EvaluationResult]) -> IncorrectRetrievalsAnalysis:
    """Compute analysis of incorrect retrievals."""
    incorrect_results = [r for r in results if not r.correct_chunk_retrieved]
    incorrect_count = len(incorrect_results)

    if incorrect_count == 0:
        return IncorrectRetrievalsAnalysis(
            incorrect_retrievals_count=0,
            avg_score_incorrect=0.0,
            datasets_with_incorrect_retrievals=[],
        )

    # Compute average score of incorrect retrievals
    incorrect_scores = []
    for result in incorrect_results:
        if result.top_k_scores:
            incorrect_scores.append(max(result.top_k_scores))

    avg_score = np.mean(incorrect_scores) if incorrect_scores else 0.0

    # Count incorrect retrievals per dataset and sort by frequency
    dataset_counts: Dict[str, int] = defaultdict(int)
    for result in incorrect_results:
        dataset_counts[result.expected_chunk.source] += 1

    # Sort datasets by number of incorrect retrievals (descending) and then by name
    sorted_datasets = sorted(
        dataset_counts.items(), key=lambda x: (-x[1], x[0])  # Sort by count desc, then name
    )

    return IncorrectRetrievalsAnalysis(
        incorrect_retrievals_count=incorrect_count,
        avg_score_incorrect=float(avg_score),
        datasets_with_incorrect_retrievals=[dataset for dataset, _ in sorted_datasets],
    )


def compute_metrics_summary(results: List[EvaluationResult], batch_id: str) -> MetricsSummary:
    """Compute summary metrics for an evaluation batch."""
    # Group results by dataset
    dataset_results = defaultdict(list)
    for result in results:
        dataset_results[result.expected_chunk.source].append(result)

    # Compute metrics per dataset
    dataset_metrics = {
        dataset: compute_dataset_metrics(dataset_results[dataset]) for dataset in dataset_results
    }

    # Compute overall metrics
    overall = compute_dataset_metrics(results)
    incorrect_analysis = compute_incorrect_analysis(results)

    # Get average retrieval time
    avg_time = np.mean([r.retrieval_time_ms for r in results])

    return MetricsSummary(
        batch_id=batch_id,
        timestamp=results[0].timestamp if results else "",
        overall_metrics={
            "recall_at_k": overall.recall_at_k,
            "mean_retrieval_time_ms": float(avg_time),
            "total_questions": len(results),
            "successful_retrievals": len(results) - incorrect_analysis.incorrect_retrievals_count,
        },
        dataset_metrics=dataset_metrics,
        incorrect_analysis=incorrect_analysis,
    )

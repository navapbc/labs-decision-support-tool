"""Metrics computation for evaluation results."""

from typing import List, Dict, Tuple
from collections import defaultdict
import numpy as np
from ..models.metrics import (
    EvaluationResult,
    MetricsSummary,
    DatasetMetrics,
    ErrorAnalysis
)

def compute_mrr(ranks: List[int]) -> float:
    """Compute Mean Reciprocal Rank from a list of correct answer ranks."""
    if not ranks:
        return 0.0
    return sum(1.0 / rank for rank in ranks) / len(ranks)

def compute_dataset_metrics(results: List[EvaluationResult]) -> DatasetMetrics:
    """Compute metrics for a specific dataset."""
    if not results:
        return DatasetMetrics(
            precision_at_k=0.0,
            recall_at_k=0.0,
            relevance=0.0,
            sample_size=0
        )
    
    total = len(results)
    correct = sum(1 for r in results if r.correct_chunk_retrieved)
    
    # Compute average relevance from top_k_scores
    relevance = sum(
        sum(r.top_k_scores) / len(r.top_k_scores)  # Average score per result
        for r in results
    ) / total
    
    return DatasetMetrics(
        precision_at_k=correct / total,
        recall_at_k=correct / total,  # Same as precision for single-answer case
        relevance=relevance,
        sample_size=total
    )

def compute_error_analysis(results: List[EvaluationResult]) -> ErrorAnalysis:
    """Compute error analysis metrics."""
    failed_results = [r for r in results if not r.correct_chunk_retrieved]
    failed_count = len(failed_results)
    
    if failed_count == 0:
        return ErrorAnalysis(
            failed_retrievals=0,
            avg_score_failed=0.0,
            common_failure_datasets=[]
        )
    
    # Compute average score of failed retrievals
    failed_scores = []
    for result in failed_results:
        if result.top_k_scores:
            failed_scores.append(max(result.top_k_scores))
    
    avg_score = np.mean(failed_scores) if failed_scores else 0.0
    
    # Find most common failure datasets
    dataset_failures = defaultdict(int)
    for result in failed_results:
        dataset_failures[result.document_info.source] += 1
    
    # Sort by frequency and get top 3
    common_datasets = sorted(
        dataset_failures.items(),
        key=lambda x: (-x[1], x[0])  # Sort by count desc, then name
    )[:3]
    
    return ErrorAnalysis(
        failed_retrievals=failed_count,
        avg_score_failed=float(avg_score),
        common_failure_datasets=[d[0] for d in common_datasets]
    )

def compute_metrics_summary(
    results: List[EvaluationResult],
    batch_id: str
) -> MetricsSummary:
    """Compute summary metrics for an evaluation batch."""
    # Group results by dataset
    dataset_results = defaultdict(list)
    for result in results:
        dataset_results[result.document_info.source].append(result)
    
    # Compute metrics per dataset
    dataset_metrics = {
        dataset: compute_dataset_metrics(dataset_results[dataset])
        for dataset in dataset_results
    }
    
    # Compute overall metrics
    overall = compute_dataset_metrics(results)
    error_analysis = compute_error_analysis(results)
    
    # Get average retrieval time
    avg_time = np.mean([r.retrieval_time_ms for r in results])
    
    return MetricsSummary(
        batch_id=batch_id,
        timestamp=results[0].timestamp if results else "",
        overall_metrics={
            "precision_at_k": overall.precision_at_k,
            "recall_at_k": overall.recall_at_k,
            "mean_retrieval_time_ms": float(avg_time),
            "total_questions": len(results),
            "successful_retrievals": len(results) - error_analysis.failed_retrievals
        },
        dataset_metrics=dataset_metrics,
        error_analysis=error_analysis
    )

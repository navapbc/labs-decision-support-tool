#!/usr/bin/env python3
"""Command-line interface for running evaluations."""

import argparse
import json
import os
from typing import Any, Callable, List, Optional, Sequence

from src.retrieve import retrieve_with_scores

from .evaluation.runner import run_evaluation


def parse_k_values(k_str: str) -> List[int]:
    """Parse comma-separated k values."""
    return [int(k) for k in k_str.split(",")]


def create_retrieval_function(min_score: float) -> Callable[[str, int], Sequence[Any]]:
    """Create retrieval function with configured min_score."""

    def retrieval_func(query: str, k: int) -> Sequence[Any]:
        return retrieve_with_scores(query, k, min_score)

    return retrieval_func


def main() -> None:
    """Run the CLI application."""
    parser = argparse.ArgumentParser(description="Run precision-recall evaluation")
    parser.add_argument(
        "--dataset",
        type=str,
        help="Dataset to evaluate (imagine_la, la_policy, or all)",
        required=True,
    )
    parser.add_argument("--k", type=str, default="5,10,25", help="Comma-separated list of k values")
    parser.add_argument(
        "--questions-file",
        type=str,
        default="src/metrics/data/question_answer_pairs.csv",
        help="Path to questions CSV file",
    )
    parser.add_argument("--sampling", type=float, help="Fraction of questions to sample (e.g. 0.1)")
    parser.add_argument(
        "--min-score", type=float, default=-1.0, help="Minimum similarity score for retrieval"
    )
    parser.add_argument("--commit", type=str, help="Git commit hash of the code being evaluated")

    args = parser.parse_args()

    # Set up dataset filter
    dataset_filter = None if args.dataset == "all" else [args.dataset]

    # Set up log directory in src/metrics/logs
    log_dir = os.path.join("src", "metrics", "logs")
    os.makedirs(log_dir, exist_ok=True)
    print(f"Writing logs to: {os.path.abspath(log_dir)}")

    # Set up retrieval function with min_score
    retrieval_func = create_retrieval_function(args.min_score)

    # Run evaluation
    try:
        run_evaluation(
            questions_file=args.questions_file,
            k_values=parse_k_values(args.k),
            retrieval_func=retrieval_func,
            dataset_filter=dataset_filter,
            sample_fraction=args.sampling,
            log_dir=log_dir,
            commit=args.commit,  # Pass commit hash to evaluation
        )

        # Print latest results
        latest_results = None
        latest_timestamp: Optional[str] = None
        for filename in os.listdir(log_dir):
            if filename.startswith("metrics_"):
                filepath = os.path.join(log_dir, filename)
                with open(filepath) as f:
                    metrics = json.load(f)
                    timestamp = metrics["timestamp"]
                    # Update latest if this is the first or a newer timestamp
                    if latest_timestamp is None or timestamp > latest_timestamp:
                        latest_timestamp = timestamp
                        latest_results = metrics

        if latest_results:
            print("\nLatest Evaluation Results:")
            print("=" * 50)
            print(f"Batch ID: {latest_results['batch_id']}")
            print(f"Timestamp: {latest_results['timestamp']}")
            if "commit" in latest_results:
                print(f"Commit: {latest_results['commit']}")
            print("\nOverall Metrics:")
            for metric, value in latest_results["overall_metrics"].items():
                print(f"  {metric}: {value:.4f}")
            print("\nDataset Metrics:")
            for dataset, metrics in latest_results["dataset_metrics"].items():
                print(f"\n  {dataset}:")
                print(f"    Recall@k: {metrics['recall_at_k']:.4f}")
                print(f"    Sample size: {metrics['sample_size']}")
            print("\nIncorrect Retrievals Analysis:")
            analysis = latest_results["overall_metrics"]["incorrect_retrievals_analysis"]
            print(f"  Incorrect retrievals: {analysis['incorrect_retrievals_count']}")
            print(
                f"  Average score for incorrect retrievals: {analysis['avg_score_incorrect']:.4f}"
            )
            print(
                f"  Datasets with incorrect retrievals: {', '.join(analysis['datasets_with_incorrect_retrievals'])}"
            )
    except Exception as e:
        print(f"Error running evaluation: {str(e)}")
        raise


if __name__ == "__main__":
    main()

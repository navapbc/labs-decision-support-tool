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
        return retrieve_with_scores(query=query, retrieval_k=k, retrieval_k_min_score=min_score)

    return retrieval_func


def format_metric_value(value: Any) -> str:
    """Format a metric value for display."""
    if isinstance(value, (float, int)):
        return f"{value:.4f}"
    return str(value)


def main() -> None:
    """Run the CLI application."""
    parser = argparse.ArgumentParser(description="Run precision-recall evaluation")
    parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",
        # TODO: We currently only support 'imagine_la' and 'la_policy' datasets.
        # This will be expanded to include other datasets (ca_wic, edd, etc.) as we add more evaluation data.
        help="One or more datasets to evaluate (e.g., imagine_la la_policy). If not specified, evaluates all datasets.",
        required=False,
        default=None,
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[5, 10, 25],
        help="One or more k values to evaluate (e.g., 5 10 25)",
    )
    parser.add_argument(
        "--questions-file",
        type=str,
        default="src/metrics/data/question_answer_pairs.csv",
        help="Path to questions CSV file",
    )
    parser.add_argument(
        "--min-score", type=float, default=-1.0, help="Minimum similarity score for retrieval"
    )
    parser.add_argument("--sampling", type=float, help="Fraction of questions to sample (e.g. 0.1)")
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Random seed for reproducible sampling (only used if sampling is specified)",
    )
    parser.add_argument(
        "--commit",
        type=str,
        help="Git commit hash of the code being evaluated",
    )

    args = parser.parse_args()

    # Set up dataset filter - None means all datasets
    dataset_filter = args.dataset

    # Evaluation results stored in src/metrics/logs/YYYY-MM-DD/
    # See README.md for details on log storage and structure
    log_dir = os.path.join("src", "metrics", "logs")
    os.makedirs(log_dir, exist_ok=True)
    print(f"Writing logs to: {os.path.abspath(log_dir)}")

    # Set up retrieval function with min_score
    retrieval_func = create_retrieval_function(args.min_score)

    # Run evaluation
    try:
        run_evaluation(
            questions_file=args.questions_file,
            k_values=args.k,
            retrieval_func=retrieval_func,
            dataset_filter=dataset_filter,
            sample_fraction=args.sampling,
            random_seed=args.random_seed,
            log_dir=log_dir,
            commit=args.commit,
        )

        # Print latest results
        latest_results = None
        latest_timestamp: Optional[str] = None
        for filename in os.listdir(log_dir):
            if filename.startswith("metrics_"):
                filepath = os.path.join(log_dir, filename)
                with open(filepath, "r") as f:
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
            print("\nOverall Metrics:")
            for metric, value in latest_results["overall_metrics"].items():
                if metric != "incorrect_retrievals_analysis":
                    print(f"  {metric}: {format_metric_value(value)}")

            # Print incorrect retrievals analysis separately
            if "incorrect_retrievals_analysis" in latest_results["overall_metrics"]:
                analysis = latest_results["overall_metrics"]["incorrect_retrievals_analysis"]
                print("\nIncorrect Retrievals Analysis:")
                print(f"  Incorrect retrievals: {analysis['incorrect_retrievals_count']}")
                print(
                    f"  Average score for incorrect retrievals: {format_metric_value(analysis['avg_score_incorrect'])}"
                )
                print(
                    f"  Datasets with incorrect retrievals: {', '.join(analysis['datasets_with_incorrect_retrievals'])}"
                )

            print("\nDataset Metrics:")
            for dataset, metrics in latest_results["dataset_metrics"].items():
                print(f"\n  {dataset}:")
                print(f"    Recall@k: {format_metric_value(metrics['recall_at_k'])}")
                print(f"    Sample size: {metrics['sample_size']}")
    except Exception as e:
        print(f"Error running evaluation: {str(e)}")
        raise


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CLI for running evaluation metrics."""

import argparse
from pathlib import Path
from typing import Any

from ..metrics.runner import create_retrieval_function, run_evaluation

# Map CLI dataset names to DB dataset names
DATASET_MAPPING = {
    "imagine_la": "Imagine LA",
    "la_policy": "DPSS Policy",
    "ca_ftb": "CA FTB",
    "irs": "IRS",
    "kyb": "Keep Your Benefits",
    "wic": "WIC",
}


def format_metric_value(value: Any) -> str:
    """Format a metric value for display."""
    if isinstance(value, (float, int)):
        return f"{value:.4f}"
    return str(value)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(description="Evaluation Metrics Tools")

    parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",
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
        type=Path,
        default=Path("src/evaluation/data/qa_pairs/question_answer_pairs.csv"),
        help="Path to questions CSV file",
    )
    parser.add_argument(
        "--min-score", type=float, default=-1.0, help="Minimum similarity score for retrieval"
    )
    parser.add_argument("--sampling", type=float, help="Fraction of questions to sample (e.g. 0.1)")
    parser.add_argument("--random-seed", type=int, help="Random seed for reproducible sampling")
    parser.add_argument("--commit", type=str, help="Git commit hash for tracking evaluation runs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/evaluation/data"),
        help="Base directory for evaluation results",
    )

    return parser


def main() -> None:
    """Run the metrics evaluation CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Map CLI dataset names to DB names if specified
    if args.dataset:
        db_datasets = [DATASET_MAPPING.get(d.lower(), d) for d in args.dataset]
        print(f"Using datasets (after mapping): {db_datasets}")
    else:
        db_datasets = None

    # Set up evaluation logs directory
    log_dir = args.output_dir / "logs" / "evaluations"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing logs to: {log_dir.absolute()}")

    try:
        # Create retrieval function with min_score
        retrieval_func = create_retrieval_function(args.min_score)

        # Run evaluation
        run_evaluation(
            questions_file=str(args.questions_file),
            k_values=args.k,
            dataset_filter=db_datasets,
            sample_fraction=args.sampling,
            random_seed=args.random_seed,
            min_score=args.min_score,
            retrieval_func=retrieval_func,
            log_dir=str(log_dir),
            commit=args.commit,
        )

    except Exception as e:
        print(f"Error running evaluation: {str(e)}")
        raise


if __name__ == "__main__":
    main()

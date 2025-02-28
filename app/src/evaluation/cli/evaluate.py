#!/usr/bin/env python3
"""CLI for QA evaluation."""

import argparse
from pathlib import Path

from ..metrics.runner import run_evaluation

# Map CLI dataset names to DB dataset names
DATASET_MAPPING = {
    "imagine_la": "Imagine LA",
    "la_policy": "DPSS Policy",
    "ca_ftb": "CA FTB",
    "irs": "IRS",
    "kyb": "Keep Your Benefits",
    "wic": "WIC",
}


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the evaluate CLI."""
    parser = argparse.ArgumentParser(description="QA Evaluation Tool")

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
        "--qa-pairs-version",
        type=str,
        help="Version ID of QA pairs to evaluate. Defaults to latest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/evaluation/data"),
        help="Base directory containing QA pairs and evaluation results",
    )
    parser.add_argument("--sampling", type=float, help="Fraction of questions to sample (e.g. 0.1)")
    parser.add_argument("--random-seed", type=int, help="Random seed for reproducible sampling")
    parser.add_argument("--commit", type=str, help="Git commit hash for tracking evaluation runs")

    return parser


def main() -> None:
    """Run the QA evaluation CLI application."""
    parser = create_parser()
    args = parser.parse_args()

    # Map CLI dataset names to DB names if specified
    if args.dataset:
        db_datasets = [DATASET_MAPPING.get(d.lower(), d) for d in args.dataset]
        print(f"Using datasets (after mapping): {db_datasets}")
    else:
        db_datasets = None

    base_path = args.output_dir if hasattr(args, "output_dir") else Path("src/evaluation/data")
    qa_pairs_dir = base_path / "qa_pairs"

    try:
        # Use the qa_pairs.csv file
        qa_pairs_path = qa_pairs_dir / "qa_pairs.csv"

        print(f"Using QA pairs from: {qa_pairs_path}")

        # Use evaluation logs directory within our module's data directory
        eval_logs_dir = base_path / "logs" / "evaluations"

        run_evaluation(
            questions_file=str(qa_pairs_path),
            k_values=args.k,
            dataset_filter=db_datasets,
            sample_fraction=args.sampling,
            random_seed=args.random_seed,
            log_dir=str(eval_logs_dir),  # Pass the module-specific log directory
            commit=args.commit,
        )
    except Exception as e:
        print(f"Error running evaluation: {str(e)}")
        raise


if __name__ == "__main__":
    main()

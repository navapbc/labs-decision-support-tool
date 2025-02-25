#!/usr/bin/env python3
"""Unified CLI for QA generation and evaluation."""

import argparse
from pathlib import Path

from ..metrics.runner import create_retrieval_function, run_evaluation
from ..qa_generation.config import GenerationConfig
from ..qa_generation.runner import run_generation
from ..utils.storage import QAPairStorage

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
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(description="QA Generation and Evaluation Tools")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # QA Generation command
    gen_parser = subparsers.add_parser("generate", help="Generate QA pairs from documents")
    gen_parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",
        help="One or more datasets to generate QA pairs for (e.g., imagine_la la_policy). If not specified, generates for all datasets.",
        required=False,
        default=None,
    )
    gen_parser.add_argument(
        "--sampling", type=float, help="Fraction of documents to sample (e.g. 0.1)"
    )
    gen_parser.add_argument("--random-seed", type=int, help="Random seed for reproducible sampling")
    gen_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/evaluation/data"),
        help="Base directory for storing QA pairs and evaluation results",
    )
    gen_parser.add_argument(
        "--llm", type=str, default="gpt-4o-mini", help="LLM model to use for QA generation"
    )
    gen_parser.add_argument(
        "--commit", type=str, help="Git commit hash for tracking generation runs"
    )

    # Evaluation command
    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation on QA pairs")
    eval_parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",
        help="One or more datasets to evaluate (e.g., imagine_la la_policy). If not specified, evaluates all datasets.",
        required=False,
        default=None,
    )
    eval_parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[5, 10, 25],
        help="One or more k values to evaluate (e.g., 5 10 25)",
    )
    eval_parser.add_argument(
        "--qa-pairs-version",
        type=str,
        help="Version ID of QA pairs to evaluate. Defaults to latest.",
    )
    eval_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/evaluation/data"),
        help="Base directory containing QA pairs and evaluation results",
    )
    eval_parser.add_argument(
        "--min-score", type=float, default=-1.0, help="Minimum similarity score for retrieval"
    )
    eval_parser.add_argument(
        "--sampling", type=float, help="Fraction of questions to sample (e.g. 0.1)"
    )
    eval_parser.add_argument(
        "--random-seed", type=int, help="Random seed for reproducible sampling"
    )
    eval_parser.add_argument(
        "--commit", type=str, help="Git commit hash for tracking evaluation runs"
    )

    return parser


def main() -> None:
    """Run the CLI application."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Map CLI dataset names to DB names if specified
    if args.dataset:
        db_datasets = [DATASET_MAPPING.get(d.lower(), d) for d in args.dataset]
        print(f"Using datasets (after mapping): {db_datasets}")
    else:
        db_datasets = None

    # Use consistent base path for both commands
    base_path = args.output_dir if hasattr(args, "output_dir") else Path("src/evaluation/data")
    qa_pairs_dir = base_path / "qa_pairs"

    if args.command == "generate":
        config = GenerationConfig.from_cli_args(args)
        try:
            qa_pairs_path = run_generation(
                config=config,
                output_dir=base_path,  # Pass base path, not qa_pairs_dir
                dataset_filter=db_datasets,
                sample_fraction=args.sampling,
                random_seed=args.random_seed,
                git_commit=args.commit,
            )
            print(f"Generated QA pairs saved to: {qa_pairs_path}")

        except ValueError as e:
            if "No documents found" in str(e):
                print(
                    f"No documents found matching criteria. Available datasets: {list(DATASET_MAPPING.keys())}"
                )
                return
            raise

    elif args.command == "evaluate":
        try:
            # Get QA pairs version using same output_dir as generation
            storage = QAPairStorage(qa_pairs_dir)
            try:
                version_id = args.qa_pairs_version or storage.get_latest_version()
            except ValueError as e:
                print(f"Error running evaluation: {str(e)}")
                raise

            version_dir = storage.get_version_path(version_id)
            qa_pairs_path = version_dir / "qa_pairs.csv"

            print(f"Using QA pairs from: {qa_pairs_path}")

            # Create retrieval function with min_score
            retrieval_func = create_retrieval_function(args.min_score)

            # Use evaluation logs directory within our module's data directory
            eval_logs_dir = base_path / "logs" / "evaluations"

            run_evaluation(
                questions_file=str(qa_pairs_path),
                k_values=args.k,
                dataset_filter=db_datasets,
                sample_fraction=args.sampling,
                random_seed=args.random_seed,
                min_score=args.min_score,
                retrieval_func=retrieval_func,
                log_dir=str(eval_logs_dir),  # Pass the module-specific log directory
                commit=args.commit,
            )
        except Exception as e:
            print(f"Error running evaluation: {str(e)}")
            raise


if __name__ == "__main__":
    main()

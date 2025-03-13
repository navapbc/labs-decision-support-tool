#!/usr/bin/env python3
"""CLI for QA generation from documents."""

import argparse
from datetime import datetime
from pathlib import Path

from ..data_models import QAPairVersion
from ..qa_generation.runner import run_generation
from ..utils.storage import QAPairStorage

# Map CLI dataset names to DB dataset names
DATASET_MAPPING = {
    "imagine_la": "Imagine LA",
    "benefits_hub": "Benefits Information Hub",
    "ca_edd": "CA EDD",
    "ca_ftb": "CA FTB",
    "covered_ca": "Covered California",
    "la_policy": "DPSS Policy",
    "irs": "IRS",
    "kyb": "Keep Your Benefits",
    "wic": "WIC",
}


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the generate CLI."""
    parser = argparse.ArgumentParser(description="QA Generation Tool")

    parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",
        help="One or more datasets to generate QA pairs for (e.g., imagine_la la_policy). If not specified, generates for all datasets.",
        required=False,
        default=None,
    )
    parser.add_argument("--sampling", type=float, help="Fraction of documents to sample (e.g. 0.1)")
    parser.add_argument("--min-samples", type=int, help="Minimum number of samples per dataset")
    parser.add_argument("--random-seed", type=int, help="Random seed for reproducible sampling")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/evaluation/data"),
        help="Base directory for storing QA pairs and evaluation results",
    )
    parser.add_argument(
        "--llm", type=str, default="gpt-4o-mini", help="LLM model to use for QA generation"
    )
    parser.add_argument("--commit", type=str, help="Git commit hash for tracking generation runs")

    return parser


def main() -> None:
    """Run the QA generation CLI application."""
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
        # Create version info for this generation run
        version = QAPairVersion(
            version_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            llm_model=args.llm,
            timestamp=datetime.utcnow(),
        )

        # Generate QA pairs
        qa_pairs = run_generation(
            llm_model=args.llm,
            output_dir=base_path,
            dataset_filter=db_datasets,
            sample_fraction=args.sampling,
            min_samples=args.min_samples,
            random_seed=args.random_seed,
            version=version,  # Pass version info to runner
        )

        # Save QA pairs with versioning
        storage = QAPairStorage(qa_pairs_dir)
        qa_pairs_path = storage.save_qa_pairs(
            qa_pairs=qa_pairs,
            version_id=version.version_id,
            git_commit=args.commit,
        )

        print(f"Generated QA pairs saved to: {qa_pairs_path}")
        print(f"Version ID: {version.version_id}")

    except ValueError as e:
        if "No documents found" in str(e):
            print(
                f"No documents found matching criteria. Available datasets: {list(DATASET_MAPPING.keys())}"
            )
            return
        raise


if __name__ == "__main__":
    main()

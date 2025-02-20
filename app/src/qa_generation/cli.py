import argparse
from datetime import datetime
from pathlib import Path
from src.db.models.document import Document
from src.metrics.evaluation.runner import run_evaluation
from src.app_config import app_config
from .config import GenerationConfig, QuestionSource
from .runner import run_generation

# Map CLI dataset names to DB dataset names
DATASET_MAPPING = {
    "imagine_la": "Imagine LA",
    "la_policy": "DPSS Policy",
    "ca_ftb": "CA FTB",
    "irs": "IRS",
    "kyb": "Keep Your Benefits",
    "wic": "WIC"
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate QA pairs from documents")
    
    parser.add_argument(
        "--dataset",
        type=str,
        nargs="+",  # Accept multiple datasets like metrics CLI
        help="One or more datasets to generate QA pairs for (e.g., imagine_la la_policy). If not specified, generates for all datasets.",
        required=False,
        default=None,
    )
    parser.add_argument(
        "--sampling",
        type=float,
        help="Fraction of documents to sample (e.g. 0.1)"
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/metrics/data/qa_pairs"),
        help="Directory to store QA pairs"
    )
    parser.add_argument(
        "--llm",
        type=str,
        default="gpt-4o-mini",
        help="LLM model to use for QA generation"
    )
    
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    config = GenerationConfig.from_cli_args(args)
    
    # Map CLI names to DB names
    if args.dataset:
        db_datasets = [DATASET_MAPPING.get(d.lower(), d) for d in args.dataset]
        print(f"Querying for datasets (after mapping): {db_datasets}")
    else:
        db_datasets = None
    
    try:
        run_generation(
            config=config,
            output_dir=args.output_dir,
            dataset_filter=db_datasets,
            sample_fraction=args.sampling,
            random_seed=args.random_seed,
        )
    except ValueError as e:
        if "No documents found" in str(e):
            print(f"No documents found matching criteria. Available datasets: {list(DATASET_MAPPING.keys())}")
            return
        raise

if __name__ == "__main__":
    main() 
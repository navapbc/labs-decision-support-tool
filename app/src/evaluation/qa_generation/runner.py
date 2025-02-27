import csv
from dataclasses import asdict, fields
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import joinedload

from src.app_config import app_config
from src.db.models.document import Document
from src.evaluation.data_models import QAPair
from src.util.sampling import get_stratified_sample

from .config import GenerationConfig
from .generator import QAGenerator


def save_qa_pairs(output_dir: Path, qa_pairs: List[QAPair]) -> Path:
    """Save QA pairs to a CSV file.

    Args:
        output_dir: Directory to save the CSV file
        qa_pairs: List of QA pairs to save

    Returns:
        Path to saved QA pairs CSV
    """
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create QA pairs CSV file
    csv_path = output_dir / "qa_pairs.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(QAPair)])
        writer.writeheader()
        writer.writerows(asdict(pair) for pair in qa_pairs)

    return csv_path


def run_generation(
    config: GenerationConfig,
    output_dir: Path,
    dataset_filter: Optional[List[str]] = None,
    sample_fraction: Optional[float] = None,
    random_seed: Optional[int] = None,
    git_commit: Optional[str] = None,
) -> Path:
    """Run QA pair generation with given configuration.

    Args:
        config: Generation configuration
        output_dir: Directory to store output files
        dataset_filter: List of dataset names to include
        sample_fraction: Fraction of documents to sample
        random_seed: Random seed for reproducible sampling
        git_commit: Git commit hash for tracking generation runs (not used in this simplified version)

    Returns:
        Path to generated QA pairs CSV
    """
    # Validate LLM model is specified
    if not config.llm_model:
        raise ValueError("No LLM model specified for QA generation")

    # Create generator
    generator = QAGenerator(config)

    # Load documents from DB
    with app_config.db_session() as session:
        query = session.query(Document)
        if dataset_filter:
            query = query.filter(Document.dataset.in_(dataset_filter)).options(
                joinedload(Document.chunks)
            )
        documents = query.all()

        if not documents:
            raise ValueError("No documents found matching filter criteria")

        # Sample documents if requested
        if sample_fraction:
            documents = get_stratified_sample(
                documents,
                sample_fraction=sample_fraction,
                random_seed=random_seed,
                key_func=lambda d: d.dataset,
            )

        # Generate QA pairs
        qa_pairs = generator.generate_from_documents(documents)

        # Save QA pairs
        qa_pairs_path = save_qa_pairs(output_dir / "qa_pairs", qa_pairs)

        print(f"Generated {len(qa_pairs)} QA pairs")

        return qa_pairs_path

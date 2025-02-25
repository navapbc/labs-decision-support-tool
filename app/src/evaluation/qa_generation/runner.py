from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import joinedload

from src.app_config import app_config
from src.db.models.document import Document
from src.util.sampling import get_stratified_sample

from ..utils.progress import ProgressTracker
from ..utils.storage import QAPairStorage
from .config import GenerationConfig
from .generator import QAGenerator


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
        git_commit: Git commit hash for tracking generation runs

    Returns:
        Path to generated QA pairs CSV
    """
    # Validate LLM model is specified
    if not config.llm_model:
        raise ValueError("No LLM model specified for QA generation")

    # Create progress tracker and generator
    progress = ProgressTracker("QA Generation")
    generator = QAGenerator(config, progress_tracker=progress)

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
        qa_pairs = list(generator.generate_from_documents(documents))

        # Save QA pairs
        storage = QAPairStorage(output_dir / "qa_pairs")
        qa_pairs_path = storage.save_qa_pairs(
            qa_pairs=qa_pairs,
            version_id=config.version_id,
            git_commit=git_commit,
        )

        # Log completion stats
        progress.log_completion(
            {
                "Total QA pairs": len(qa_pairs),
                "Output path": str(qa_pairs_path),
                "items_processed": len(qa_pairs),
            }
        )

        return qa_pairs_path

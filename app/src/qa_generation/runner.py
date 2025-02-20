from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import joinedload

from src.app_config import app_config
from src.db.models.document import Document
from src.util.sampling import get_stratified_sample
from .generator import QAGenerator
from .storage import QAPairStorage
from .config import GenerationConfig

def run_generation(
    config: GenerationConfig,
    output_dir: Path,
    dataset_filter: Optional[List[str]] = None,
    sample_fraction: Optional[float] = None,
    random_seed: Optional[int] = None,
) -> Path:
    """Run QA pair generation with given configuration.
    
    Args:
        config: Generation configuration
        output_dir: Directory to store output files
        dataset_filter: List of dataset names to include
        sample_fraction: Fraction of documents to sample
        random_seed: Random seed for reproducible sampling
        
    Returns:
        Path to generated QA pairs CSV
    """
    # Validate LLM model is specified
    if not config.llm_model:
        raise ValueError("No LLM model specified for QA generation")
    
    # Use today's date as version (matching ingestion versioning)
    dataset_version = datetime.now().strftime("%Y-%m-%d")
    
    # Generate QA pairs
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
            raise ValueError(f"No documents found matching criteria")
            
        # Sample documents if requested
        documents = get_stratified_sample(
            documents,
            sample_fraction=sample_fraction,
            random_seed=random_seed,
            key_func=lambda d: d.dataset
        )
            
        print(f"Processing {len(documents)} documents after sampling")
            
        qa_pairs = list(generator.generate_from_documents(documents))
        
        # Save with version information
        storage = QAPairStorage(output_dir)
        qa_pairs_path = storage.save_qa_pairs(
            qa_pairs=qa_pairs,
            version_id=dataset_version,
        )
        
        # Log completion
        generator.progress.log_completion(qa_pairs_path, len(qa_pairs))
        
        return qa_pairs_path 
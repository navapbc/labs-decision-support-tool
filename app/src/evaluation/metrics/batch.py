"""
Batch processing for evaluation runs.
Not to be confused with batch_process.py (used via the API).
"""

import random
import subprocess
from collections import defaultdict
from typing import Dict, List, Optional
from pathlib import Path

from ..models.metrics import BatchConfig, EvaluationConfig, QAGenerationInfo, SoftwareInfo
from ..utils.storage import QAPairStorage
from src.util.sampling import get_stratified_sample


def get_git_commit() -> str:
    """Get current git commit hash.

    Raises:
        RuntimeError: If unable to get git commit hash
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception as err:
        raise RuntimeError(f"Failed to get git commit hash: {str(err)}") from err


def get_package_version() -> str:
    """Get current package version.

    Raises:
        RuntimeError: If unable to read version from pyproject.toml
    """
    try:
        with open("pyproject.toml", "r") as f:
            for line in f:
                if line.startswith("version"):
                    return line.split("=")[1].strip().strip("\"'")
            raise RuntimeError("No version field found in pyproject.toml")
    except Exception as err:
        raise RuntimeError(
            f"Failed to get package version from pyproject.toml: {str(err)}"
        ) from err


def create_batch_config(
    k_value: int,
    qa_pairs_path: Path,
    dataset_filter: Optional[List[str]] = None,
    git_commit: Optional[str] = None,
) -> BatchConfig:
    """Create a new batch configuration.
    
    Args:
        k_value: Number of chunks to retrieve
        qa_pairs_path: Path to QA pairs CSV file
        dataset_filter: Optional list of datasets to filter by
        git_commit: Optional git commit hash
        
    Returns:
        BatchConfig with evaluation settings and QA generation metadata
    """
    # Get QA generation metadata
    storage = QAPairStorage(qa_pairs_path.parent.parent)  # Go up two levels to qa_pairs dir
    version_id = qa_pairs_path.parent.name
    qa_metadata = storage.get_version_metadata(version_id)
    
    qa_generation_info = QAGenerationInfo(
        version_id=qa_metadata["version_id"],
        timestamp=qa_metadata["timestamp"],
        llm_model=qa_metadata["llm_model"],
        total_pairs=qa_metadata["total_pairs"],
        datasets=qa_metadata["datasets"],
        git_commit=qa_metadata["git_commit"],
    )
    
    eval_config = EvaluationConfig(
        k_value=k_value,
        num_samples=0,  # Will be updated when questions are loaded
        dataset_filter=dataset_filter or [],
    )
    
    software_info = SoftwareInfo(
        package_version=get_package_version(),
        git_commit=git_commit or get_git_commit(),
    )
    
    return BatchConfig(
        evaluation_config=eval_config,
        software_info=software_info,
        qa_generation_info=qa_generation_info,
    )


def stratified_sample(
    questions: List[Dict],
    sample_fraction: Optional[float] = None,
    random_seed: Optional[int] = None,
) -> List[Dict]:
    """Sample questions while maintaining dataset proportions."""
    return get_stratified_sample(
        questions,
        sample_fraction=sample_fraction,
        random_seed=random_seed,
        key_func=lambda q: q["dataset"]
    )


def filter_questions(
    questions: List[Dict], dataset_filter: Optional[List[str]] = None
) -> List[Dict]:
    """Filter questions by dataset.

    Args:
        questions: List of questions to filter
        dataset_filter: List of dataset names to include

    Returns:
        Filtered questions
    """
    if not dataset_filter:
        return questions

    # Map CLI dataset names to actual dataset names in CSV
    dataset_mapping = {
        "imagine_la": "Benefits Information Hub",
        "la_policy": "LA County Policy",
    }

    # Convert input to lowercase for case-insensitive matching
    mapped_datasets = [dataset_mapping.get(d.lower(), d) for d in dataset_filter]
    print(f"Filtering for datasets (after mapping): {mapped_datasets}")

    filtered = [q for q in questions if q["dataset"] in mapped_datasets]
    print(f"Found {len(filtered)} questions for datasets {mapped_datasets}")
    return filtered

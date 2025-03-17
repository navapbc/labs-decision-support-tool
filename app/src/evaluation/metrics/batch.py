"""
Batch processing for evaluation runs.
"""

import subprocess
from typing import Dict, List, Optional

from src.evaluation.data_models import BatchConfig, EvaluationConfig, SoftwareInfo
from src.evaluation.utils.dataset_mapping import map_dataset_name


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
    k_value: int, dataset_filter: Optional[List[str]] = None, git_commit: Optional[str] = None
) -> BatchConfig:
    """Create a new batch configuration."""
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

    # Convert input to lowercase for case-insensitive matching
    mapped_datasets = [map_dataset_name(d) for d in dataset_filter]
    print(f"Filtering for datasets (after mapping): {mapped_datasets}")

    filtered = [q for q in questions if q["dataset"] in mapped_datasets]
    print(f"Found {len(filtered)} questions for datasets {mapped_datasets}")
    return filtered

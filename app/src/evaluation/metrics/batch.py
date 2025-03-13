"""
Batch processing for evaluation runs.
Not to be confused with batch_process.py (used via the API).
"""

import random
import subprocess
from collections import defaultdict
from typing import Dict, List, Optional

from src.evaluation.data_models import BatchConfig, EvaluationConfig, SoftwareInfo


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


def stratified_sample(
    questions: List[Dict],
    sample_fraction: Optional[float] = None,
    min_samples: Optional[int] = None,
    random_seed: Optional[int] = None,
) -> List[Dict]:
    """Take a stratified sample of questions based on dataset.

    Args:
        questions: List of questions to sample from
        sample_fraction: Optional fraction of questions to sample (0-1)
        min_samples: Optional minimum number of questions per dataset
        random_seed: Optional seed for random sampling to make runs reproducible

    Returns:
        Sampled questions maintaining dataset proportions. The sampling is stratified,
        meaning it maintains the relative proportions of questions from each dataset
        while ensuring at least min_samples questions from each dataset (if specified).
    """
    if not sample_fraction and not min_samples:
        return questions

    # Set random seed if provided
    if random_seed is not None:
        random.seed(random_seed)

    # Group questions by dataset
    dataset_groups = defaultdict(list)
    for q in questions:
        dataset_groups[q["dataset"]].append(q)

    # Sample from each dataset
    sampled_questions = []
    for _, group in dataset_groups.items():
        if min_samples is not None:
            # Take all items if group size is less than or equal to min_samples
            if len(group) <= min_samples:
                sampled_questions.extend(group)
                continue

            # Otherwise, take max of min_samples and fraction-based size
            fraction_based_size = int(len(group) * (sample_fraction or 0))
            sample_size = max(min_samples, fraction_based_size)
            # Ensure we don't try to sample more items than available
            sample_size = min(sample_size, len(group))
        else:
            # Original behavior when no min_samples specified
            sample_size = max(1, int(len(group) * (sample_fraction or 1.0)))

        sampled_questions.extend(random.sample(group, sample_size))

    # Shuffle the combined sample
    random.shuffle(sampled_questions)

    # Reset random seed
    if random_seed is not None:
        random.seed()

    return sampled_questions


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

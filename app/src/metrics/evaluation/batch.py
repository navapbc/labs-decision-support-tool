"""Batch processing for evaluation runs."""

import random
import subprocess
from collections import defaultdict
from typing import Dict, List, Optional

from ..models.metrics import BatchConfig


def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_package_version() -> str:
    """Get current package version."""
    try:
        with open("pyproject.toml", "r") as f:
            for line in f:
                if line.startswith("version"):
                    return line.split("=")[1].strip().strip("\"'")
    except Exception:
        pass
    return "unknown"


def create_batch_config(
    k_value: int, dataset_filter: Optional[List[str]] = None, git_commit: Optional[str] = None
) -> BatchConfig:
    """Create a new batch configuration."""
    return BatchConfig(
        k_value=k_value,
        num_samples=0,  # Will be updated when questions are loaded
        dataset_filter=dataset_filter or [],
        package_version=get_package_version(),
        git_commit=git_commit or get_git_commit(),
    )


def stratified_sample(
    questions: List[Dict],
    sample_fraction: float,
    min_per_dataset: int = 1,
    random_seed: Optional[int] = None,
) -> List[Dict]:
    """Take a stratified sample of questions based on dataset.

    Args:
        questions: List of questions to sample from
        sample_fraction: Fraction of questions to sample (0-1)
        min_per_dataset: Minimum number of questions per dataset
        random_seed: Optional seed for random sampling to make runs reproducible

    Returns:
        Sampled questions maintaining dataset proportions. The sampling is stratified,
        meaning it maintains the relative proportions of questions from each dataset
        while ensuring at least min_per_dataset (default: 1) questions from each.
    """
    if sample_fraction >= 1.0:
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
        sample_size = max(min_per_dataset, int(len(group) * sample_fraction))
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
        "imagine_la": "Imagine LA",
        "la_policy": "LA County Policy",
    }

    # Convert input to lowercase for case-insensitive matching
    mapped_datasets = [dataset_mapping.get(d.lower(), d) for d in dataset_filter]
    print(f"Filtering for datasets (after mapping): {mapped_datasets}")

    filtered = [q for q in questions if q["dataset"] in mapped_datasets]
    print(f"Found {len(filtered)} questions for datasets {mapped_datasets}")
    return filtered

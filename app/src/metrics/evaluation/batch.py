"""Batch processing for evaluation runs."""

import os
import random
from typing import List, Dict, Optional
from collections import defaultdict
import subprocess
from ..models.metrics import BatchConfig
from ..utils.timer import measure_time

def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except:
        return "unknown"

def get_package_version() -> str:
    """Get current package version."""
    try:
        with open('pyproject.toml', 'r') as f:
            for line in f:
                if line.startswith('version'):
                    return line.split('=')[1].strip().strip('"\'')
    except:
        return "unknown"

def create_batch_config(
    k_value: int,
    dataset_filter: Optional[List[str]] = None,
    environment: str = "development"
) -> BatchConfig:
    """Create a new batch configuration."""
    return BatchConfig(
        k_value=k_value,
        num_samples=0,  # Will be updated when questions are loaded
        dataset_filter=dataset_filter or [],
        package_version=get_package_version(),
        git_commit=get_git_commit(),
        environment=environment,
        retriever_config={
            "model_name": "text-embedding-3-large",
            "chunk_size": 500,
            "overlap": 50,
            "similarity_top_k": k_value
        }
    )

def stratified_sample(
    questions: List[Dict],
    sample_fraction: float,
    min_per_dataset: int = 1
) -> List[Dict]:
    """Take a stratified sample of questions based on dataset.
    
    Args:
        questions: List of questions to sample from
        sample_fraction: Fraction of questions to sample (0-1)
        min_per_dataset: Minimum number of questions per dataset
    
    Returns:
        Sampled questions maintaining dataset proportions
    """
    if sample_fraction >= 1.0:
        return questions
    
    # Group questions by dataset
    dataset_groups = defaultdict(list)
    for q in questions:
        dataset_groups[q["dataset"]].append(q)
    
    # Sample from each dataset
    sampled_questions = []
    for dataset, group in dataset_groups.items():
        sample_size = max(
            min_per_dataset,
            int(len(group) * sample_fraction)
        )
        sampled_questions.extend(random.sample(group, sample_size))
    
    # Shuffle the combined sample
    random.shuffle(sampled_questions)
    return sampled_questions

def filter_questions(
    questions: List[Dict],
    dataset_filter: Optional[List[str]] = None
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
        'imagine_la': 'Imagine LA',
        'la_policy': 'LA County Policy'
    }
    
    mapped_datasets = [dataset_mapping.get(d, d) for d in dataset_filter]
    print(f"Filtering for datasets (after mapping): {mapped_datasets}")
    
    filtered = [q for q in questions if q["dataset"] in mapped_datasets]
    print(f"Found {len(filtered)} questions for datasets {mapped_datasets}")
    return filtered

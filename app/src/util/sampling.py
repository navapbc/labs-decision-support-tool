from typing import List, TypeVar, Sequence
import random

T = TypeVar('T')

def get_stratified_sample(
    items: Sequence[T],
    sample_fraction: float | None = None,
    random_seed: int | None = None,
    key_func: callable = lambda x: x
) -> List[T]:
    """Get a stratified sample of items.
    
    Args:
        items: Sequence of items to sample from
        sample_fraction: Fraction of items to sample (0.0 to 1.0)
        random_seed: Random seed for reproducible sampling
        key_func: Function to extract stratification key from items
    
    Returns:
        List of sampled items, maintaining relative proportions of key_func values
    """
    if not sample_fraction:
        return list(items)

    # Set random seed if provided
    if random_seed is not None:
        random.seed(random_seed)

    # Group items by key
    groups: dict[str, List[T]] = {}
    for item in items:
        key = key_func(item)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    # Sample from each group
    sampled_items = []
    for group in groups.values():
        sample_size = max(1, int(len(group) * sample_fraction))
        sampled_items.extend(random.sample(group, sample_size))

    # Reset random seed
    if random_seed is not None:
        random.seed()

    return sampled_items 
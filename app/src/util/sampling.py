import random
from collections import defaultdict
from typing import Any, Callable, List, Sequence, TypeVar

T = TypeVar("T")


def get_stratified_sample(
    items: Sequence[T],
    sample_fraction: float | None = None,
    min_samples: int | None = None,
    random_seed: int | None = None,
    key_func: Callable[[T], Any] = lambda x: x,
) -> List[T]:
    """Get a stratified sample of items with minimum samples per stratum.

    Args:
        items: Sequence of items to sample from
        sample_fraction: Fraction of items to sample (0.0 to 1.0)
        min_samples: Minimum number of samples per stratum. If a stratum has fewer items
                    than min_samples, all items from that stratum are included.
        random_seed: Random seed for reproducible sampling
        key_func: Function to extract stratification key from items

    Returns:
        List of sampled items, maintaining relative proportions of key_func values
        with at least min_samples from each stratum (if available)
    """
    if not sample_fraction and not min_samples:
        return list(items)

    # Set random seed if provided
    if random_seed is not None:
        random.seed(random_seed)

    # Group items by key using defaultdict
    groups: dict[str, List[T]] = defaultdict(list)
    for item in items:
        key = key_func(item)
        groups[key].append(item)

    # Sample from each group
    sampled_items = []
    for group in groups.values():
        group_size = len(group)
        sample_size = max(
            min_samples if min_samples is not None else 1, int(group_size * (sample_fraction or 0))
        )
        sample_size = min(sample_size, group_size)
        sampled_items.extend(random.sample(group, sample_size))

    # Reset random seed
    if random_seed is not None:
        random.seed()

    return sampled_items

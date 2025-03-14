"""Tests for sampling utility functions."""

from src.util.sampling import get_stratified_sample


def test_get_stratified_sample_no_sampling():
    """Test that when sample_fraction and min_samples are None, all items are returned."""
    items = [1, 2, 3, 4, 5]
    result = get_stratified_sample(items)
    assert result == items
    assert len(result) == len(items)


def test_get_stratified_sample_with_fraction():
    """Test sampling with a fraction."""
    items = list(range(100))
    sample_fraction = 0.1
    result = get_stratified_sample(items, sample_fraction=sample_fraction, random_seed=42)

    # Should have approximately 10% of items
    assert len(result) > 0
    assert len(result) <= len(items)


def test_get_stratified_sample_with_min_samples():
    """Test sampling with minimum samples per stratum."""
    items = (
        [{"category": "A", "value": i} for i in range(20)]
        + [{"category": "B", "value": i} for i in range(5)]
        + [{"category": "C", "value": i} for i in range(10)]
    )

    def get_category(item):
        return item["category"]

    # Sample with min_samples=8 and small fraction
    result = get_stratified_sample(
        items,
        sample_fraction=0.1,  # Would normally give 2,0,1 samples
        min_samples=8,
        random_seed=42,
        key_func=get_category,
    )

    # Count samples per category
    category_counts = {}
    for item in result:
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    # Category A should have max(8, 20*0.1)=8 samples
    assert category_counts["A"] == 8
    # Category B should have all 5 samples (less than min_samples)
    assert category_counts["B"] == 5
    # Category C should have 8 samples
    assert category_counts["C"] == 8


def test_get_stratified_sample_min_samples_with_small_groups():
    """Test min_samples with groups smaller than the minimum."""
    items = [
        {"category": "A", "value": 1},
        {"category": "A", "value": 2},
        {"category": "B", "value": 3},
        {"category": "C", "value": 4},
        {"category": "C", "value": 5},
    ]

    def get_category(item):
        return item["category"]

    # Set min_samples higher than some group sizes
    result = get_stratified_sample(
        items,
        min_samples=3,
        random_seed=42,
        key_func=get_category,
    )

    # Count samples per category
    category_counts = {}
    for item in result:
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    # Category A should have 2 samples (all items)
    assert category_counts["A"] == 2
    # Category B should have 1 sample (all items)
    assert category_counts["B"] == 1
    # Category C should have 2 samples (all items)
    assert category_counts["C"] == 2


def test_get_stratified_sample_with_key_func():
    """Test sampling with a key function for stratification."""
    items = [
        {"category": "A", "value": 1},
        {"category": "A", "value": 2},
        {"category": "A", "value": 3},
        {"category": "B", "value": 4},
        {"category": "B", "value": 5},
        {"category": "C", "value": 6},
    ]

    def get_category(item):
        return item["category"]

    # Sample 50% from each category
    result = get_stratified_sample(
        items, sample_fraction=0.5, random_seed=42, key_func=get_category
    )

    # Should have at least one item from each category
    categories = {item["category"] for item in result}
    assert "A" in categories
    assert "B" in categories
    assert "C" in categories

    # Should have fewer items than original but at least 3 (one from each category)
    assert 3 <= len(result) < len(items)


def test_get_stratified_sample_with_random_seed():
    """Test that random seed produces consistent results."""
    items = list(range(100))

    # Get two samples with the same seed
    result1 = get_stratified_sample(items, sample_fraction=0.1, random_seed=42)
    result2 = get_stratified_sample(items, sample_fraction=0.1, random_seed=42)

    # Results should be identical with the same seed
    assert result1 == result2

    # Test that the function handles the random seed parameter correctly
    assert len(result1) > 0
    assert len(result1) <= len(items)


def test_get_stratified_sample_fraction_and_min_samples():
    """Test interaction between sample_fraction and min_samples."""
    items = [{"category": "A", "value": i} for i in range(100)] + [
        {"category": "B", "value": i} for i in range(50)
    ]

    def get_category(item):
        return item["category"]

    # Sample with both fraction and min_samples
    result = get_stratified_sample(
        items,
        sample_fraction=0.2,  # Would normally give 20 and 10 samples
        min_samples=15,  # Should increase B's samples to 15
        random_seed=42,
        key_func=get_category,
    )

    # Count samples per category
    category_counts = {}
    for item in result:
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    # Category A should have 20 samples (from fraction)
    assert category_counts["A"] == 20
    # Category B should have 15 samples (from min_samples)
    assert category_counts["B"] == 15


def test_get_stratified_sample_small_groups():
    """Test sampling with very small groups."""
    items = [
        {"category": "A", "value": 1},
        {"category": "B", "value": 2},
        {"category": "C", "value": 3},
    ]

    def get_category(item):
        return item["category"]

    # Even with a small fraction, should get at least one item from each category
    result = get_stratified_sample(
        items, sample_fraction=0.1, random_seed=42, key_func=get_category
    )

    # Should have all 3 items (one from each category)
    assert len(result) == 3
    categories = {item["category"] for item in result}
    assert len(categories) == 3

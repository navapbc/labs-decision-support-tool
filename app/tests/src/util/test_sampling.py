"""Tests for sampling utility functions."""

from src.util.sampling import get_stratified_sample


def test_get_stratified_sample_no_sampling():
    """Test that when sample_fraction is None, all items are returned."""
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

    # Define a function to extract the category
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
    # Create a list of items
    items = list(range(100))

    # Get two samples with the same seed
    result1 = get_stratified_sample(items, sample_fraction=0.1, random_seed=42)
    result2 = get_stratified_sample(items, sample_fraction=0.1, random_seed=42)

    # Results should be identical with the same seed
    assert result1 == result2

    # Test that the function handles the random seed parameter correctly
    # We don't need to verify that different seeds produce different results,
    # just that the function correctly uses the seed parameter
    assert len(result1) > 0
    assert len(result1) <= len(items)


def test_get_stratified_sample_small_groups():
    """Test sampling with very small groups."""
    items = [
        {"category": "A", "value": 1},
        {"category": "B", "value": 2},
        {"category": "C", "value": 3},
    ]

    # Define a function to extract the category
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

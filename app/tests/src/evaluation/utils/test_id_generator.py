"""Tests for ID generator utilities."""

from src.evaluation.utils.id_generator import generate_stable_id


def test_generate_stable_id():
    """Test stable ID generation for QA pairs."""
    # Test that same inputs generate same UUID
    uuid1 = generate_stable_id("test question?", "test answer")
    uuid2 = generate_stable_id("test question?", "test answer")
    assert uuid1 == uuid2

    # Test that different inputs generate different UUIDs
    uuid3 = generate_stable_id("different question?", "test answer")
    assert uuid1 != uuid3

    uuid4 = generate_stable_id("test question?", "different answer")
    assert uuid1 != uuid4

    # Test that order matters
    uuid5 = generate_stable_id("test answer", "test question?")
    assert uuid1 != uuid5

    # Test with empty strings
    uuid6 = generate_stable_id("", "")
    uuid7 = generate_stable_id("", "")
    assert uuid6 == uuid7  # Should still be deterministic

    # Test with special characters
    uuid8 = generate_stable_id("question with 特殊文字?", "answer with 特殊文字!")
    uuid9 = generate_stable_id("question with 特殊文字?", "answer with 特殊文字!")
    assert uuid8 == uuid9  # Should handle special characters consistently

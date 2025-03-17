"""Tests for dataset name mapping utility."""

from src.evaluation.utils.dataset_mapping import (
    DATASET_MAPPING,
    get_dataset_mapping,
    map_dataset_name,
)


def test_get_dataset_mapping():
    """Test getting the full dataset mapping dictionary."""
    mapping = get_dataset_mapping()

    # Test that we get expected mappings
    assert mapping["ca_ftb"] == "CA FTB"
    assert mapping["edd"] == "CA EDD"
    assert mapping["la_policy"] == "DPSS Policy"

    # Test that the mapping is complete
    assert set(mapping.keys()) == {
        "ca_ftb",
        "ca_public_charge",
        "ca_wic",
        "covered_ca",
        "edd",
        "irs",
        "la_policy",
        "ssa",
    }

    # Test that the returned mapping matches the constant
    assert mapping == DATASET_MAPPING

    # Test that the mapping is not modified
    mapping["test"] = "TEST"
    assert "test" not in get_dataset_mapping()


def test_map_dataset_name():
    """Test mapping individual dataset names."""
    # Test known mappings
    assert map_dataset_name("ca_ftb") == "CA FTB"
    assert map_dataset_name("edd") == "CA EDD"
    assert map_dataset_name("la_policy") == "DPSS Policy"

    # Test case insensitivity
    assert map_dataset_name("CA_FTB") == "CA FTB"
    assert map_dataset_name("EDD") == "CA EDD"
    assert map_dataset_name("La_Policy") == "DPSS Policy"

    # Test unknown dataset names return as-is
    assert map_dataset_name("unknown") == "unknown"
    assert map_dataset_name("test_dataset") == "test_dataset"

    # Test empty string
    assert map_dataset_name("") == ""

"""Utility functions for dataset name mapping."""

from types import MappingProxyType
from typing import Mapping

# Static mapping from CLI dataset IDs to their display names
# This should match the dataset_label values in get_ingester_config
DATASET_MAPPING = MappingProxyType(
    {
        "ca_ftb": "CA FTB",
        "ca_public_charge": "Keep Your Benefits",
        "ca_wic": "WIC",
        "covered_ca": "Covered California",
        "edd": "CA EDD",
        "irs": "IRS",
        "la_policy": "DPSS Policy",
        "ssa": "SSA",
    }
)


def get_dataset_mapping() -> Mapping[str, str]:
    """Get mapping from CLI dataset names to DB dataset names.

    Returns:
        Mapping from CLI dataset names (e.g. 'ca_ftb') to DB dataset names (e.g. 'CA FTB')
    """
    return DATASET_MAPPING


def map_dataset_name(dataset_name: str) -> str:
    """Map a CLI dataset name to its DB dataset name.

    Args:
        dataset_name: CLI dataset name (e.g. 'ca_ftb')

    Returns:
        DB dataset name (e.g. 'CA FTB') if mapping exists, otherwise returns original name
    """
    return DATASET_MAPPING.get(dataset_name.lower(), dataset_name)

import logging

from . import base

logger = logging.getLogger(__name__)

# Re-export metadata
# This is used by tests to create the test database.
metadata = base.metadata

__all__ = ["metadata"]

import logging
import sys
from functools import partial

from src.app_config import app_config
from src.ingest_bem_pdfs import _ingest_bem_pdfs
from src.util.ingest_utils import IngestConfig, process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def main() -> None:
    default_config = IngestConfig(
        "bridges-administrative-manual",
        "mixed",
        "Michigan",
        app_config.resolved_public_source_base_url,
        "bridges-administrative-manual",
    )
    ingest_fn = partial(_ingest_bem_pdfs, prefix="BAM")
    process_and_ingest_sys_args(sys.argv, logger, ingest_fn, default_config)

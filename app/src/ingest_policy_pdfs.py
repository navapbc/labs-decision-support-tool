import logging
import sys

import src.adapters.db as db
from src.app_config import app_config
from src.util.file_util import get_files
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)

# Print INFO messages since this is often run from the terminal
# during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _ingest_policy_pdfs(
    db_session: db.Session,
    pdf_file_dir: str,
    doc_attribs: dict[str, str],
) -> None:
    file_list = get_files(pdf_file_dir)
    embedding_model = app_config.sentence_transformer
    for file in file_list:
        if file.endswith(".pdf"):
            logger.info(
                f"Processing pdf file: {file} at {pdf_file_dir} using {embedding_model}, {db_session}, with {doc_attribs}"
            )


def main() -> None:
    if len(sys.argv) < 5:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            sys.argv[1:],
        )
        return

    process_and_ingest_sys_args(sys, logger, _ingest_policy_pdfs)

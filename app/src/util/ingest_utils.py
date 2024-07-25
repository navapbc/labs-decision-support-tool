import getopt
from logging import Logger
from types import ModuleType
from typing import Callable

from src.app_config import app_config


def process_and_ingest_sys_args(sys: ModuleType, logger: Logger, ingestion_call: Callable) -> None:
    """Method that reads sys args and passes them into ingestion call"""

    opts, args = getopt.getopt(
        sys.argv[1:], shortopts="", longopts=["DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH)"]
    )

    dataset_id = args[0]
    benefit_program = args[1]
    benefit_region = args[2]
    pdf_file_dir = args[3]

    logger.info(
        f"Processing files {dataset_id} at {pdf_file_dir} for {benefit_program} in {benefit_region}"
    )

    doc_attribs = {
        "dataset": dataset_id,
        "program": benefit_program,
        "region": benefit_region,
    }

    with app_config.db_session() as db_session:
        ingestion_call(db_session, pdf_file_dir, doc_attribs)
        db_session.commit()

    logger.info("Finished processing")

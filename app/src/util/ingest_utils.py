import getopt
from logging import Logger
from typing import Callable

from sqlalchemy import delete, select

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Document


def _drop_existing_dataset(db_session: db.Session, dataset: str) -> bool:
    dataset_exists = db_session.execute(select(Document).where(Document.dataset == dataset)).first()
    if dataset_exists:
        db_session.execute(delete(Document).where(Document.dataset == dataset))
    return dataset_exists is not None


def process_and_ingest_sys_args(argv: list[str], logger: Logger, ingestion_call: Callable) -> None:
    """Method that reads sys args and passes them into ingestion call"""

    if len(argv[1:]) != 4:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            argv[1:],
        )
        return

    _, args = getopt.getopt(
        argv[1:], shortopts="", longopts=["DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH)"]
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
        dropped = _drop_existing_dataset(db_session, dataset_id)
        if dropped:
            logger.warning("Dropped existing dataset %s", dataset_id)
        ingestion_call(db_session, pdf_file_dir, doc_attribs)
        db_session.commit()

    logger.info("Finished processing")

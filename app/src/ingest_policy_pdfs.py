import logging
import os
import sys

from sentence_transformers import SentenceTransformer

import src.adapters.db as db
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)

# Print INFO messages since this is often run from the terminal
# during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _ingest_policy_pdfs(
    db_session: db.Session,
    embedding_model: SentenceTransformer,
    pdf_file_dir: str,
    doc_attribs: dict[str, str],
) -> None:
    directory = os.fsencode(pdf_file_dir)

    for file in os.listdir(directory):
        pdf_file_path = os.fsdecode(file)
        if pdf_file_path.endswith(".pdf"):
            logger.info(
                f"Processing pdf file: {pdf_file_path} at {pdf_file_dir} using {embedding_model}, {db_session}, with {doc_attribs}"
            )


def main() -> None:
    if len(sys.argv) < 5:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            sys.argv[1:],
        )
        return

    # TODO: improve command-line argument handling using getopt module
    dataset_id = sys.argv[1]
    benefit_program = sys.argv[2]
    benefit_region = sys.argv[3]
    pdf_file_dir = sys.argv[4]

    logger.info(
        f"Processing pdf files {dataset_id} at {pdf_file_dir} for {benefit_program} in {benefit_region}"
    )

    embedding_model = get_embedding_model()

    doc_attribs = {
        "dataset": dataset_id,
        "program": benefit_program,
        "region": benefit_region,
    }
    with db.PostgresDBClient().get_session() as db_session:
        _ingest_policy_pdfs(db_session, embedding_model, pdf_file_dir, doc_attribs)
        db_session.commit()

    logger.info("Finished processing PDFs.")

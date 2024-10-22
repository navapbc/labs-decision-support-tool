import getopt
import logging
from logging import Logger
from typing import Callable, Optional, Sequence

from sqlalchemy import delete, select

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document


def _drop_existing_dataset(db_session: db.Session, dataset: str) -> bool:
    dataset_exists = db_session.execute(select(Document).where(Document.dataset == dataset)).first()
    if dataset_exists:
        db_session.execute(delete(Document).where(Document.dataset == dataset))
    return dataset_exists is not None


def process_and_ingest_sys_args(argv: list[str], logger: Logger, ingestion_call: Callable) -> None:
    """Method that reads sys args and passes them into ingestion call"""

    # Print INFO messages since this is often run from the terminal
    # during local development
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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


def tokenize(text: str) -> list[str]:
    """
    The add_special_tokens argument is specified in PreTrainedTokenizerFast.encode_plus(), parent class of MPNetTokenizerFast.
    It defaults to True for encode_plus() but defaults to False for .tokenize().
    Setting add_special_tokens=True will add the special tokens CLS(0) and SEP(2) to the beginning and end of the input text.
    """
    tokenizer = app_config.sentence_transformer.tokenizer
    # The add_special_tokens argument is valid for only PreTrainedTokenizerFast subclasses
    return tokenizer.tokenize(text, add_special_tokens=True)


def add_embeddings(
    chunks: Sequence[Chunk], texts_to_encode: Optional[Sequence[str]] = None
) -> None:
    """
    Add embeddings to each chunk using the text from either texts_to_encode or chunk.content.
    Arguments chunks and texts_to_encode should be the same length, or texts_to_encode can be None/empty.
    This allows us to create embeddings using text other than chunk.content.
    If the corresponding texts_to_encode element evaluates to False, then chunk.content is embedded.
    """
    embedding_model = app_config.sentence_transformer

    if texts_to_encode:
        to_encode = [
            text if text else chunk.content
            for chunk, text in zip(chunks, texts_to_encode, strict=True)
        ]
    else:
        to_encode = [chunk.content for chunk in chunks]

    # Generate all the embeddings in parallel for speed
    embeddings = embedding_model.encode([text for text in to_encode], show_progress_bar=False)

    for chunk, embedding, text in zip(chunks, embeddings, to_encode, strict=True):
        chunk.mpnet_embedding = embedding
        if not chunk.tokens:
            chunk.tokens = len(tokenize(text))
        else:
            assert chunk.tokens == len(tokenize(text))
        assert (
            chunk.tokens <= embedding_model.max_seq_length
        ), f"Text too long for embedding model: {chunk.tokens} tokens: {len(chunk.content)} chars: {chunk.content[:80]}...{chunk.content[-50:]}"

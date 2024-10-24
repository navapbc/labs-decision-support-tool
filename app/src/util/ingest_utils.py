import getopt
import logging
import re
from logging import Logger
from typing import Callable, Optional, Sequence

from sqlalchemy import delete, select

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document

logger = logging.getLogger(__name__)


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
    If the corresponding texts_to_encode element evaluates to False, then chunk.content is used instead.
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


def deconstruct_list(
    markdown: str, has_intro_sentence: bool = False, list_delimiter: str = r"^( *[\-\*\+] )"
) -> tuple[str, list[str]]:
    "Deconstruct a list of items into an introductory sentence and a list of items"
    splits = re.split(list_delimiter, markdown, flags=re.MULTILINE)
    if has_intro_sentence or not markdown.startswith(list_delimiter):
        intro_sentence = splits[0]
        splits = splits[1:]
    else:
        intro_sentence = ""

    # Reconstruct each list item
    list_items = [(splits[a] + splits[a + 1]) for a in range(0, len(splits), 2)]
    return intro_sentence, list_items


def reconstruct_list(
    token_limit: int,
    intro_sentence: str,
    list_items: Sequence[str],
    join_delimiter: str = "",
) -> list[str]:
    "Reconstruct a list of items into chunks (with same intro_sentence) having up to a token limit each"
    # Before the set of list items, there should be a blank line
    intro_sentence = _ensure_blank_line_suffix(intro_sentence)

    item_max_seq_length = token_limit - len(tokenize(intro_sentence))
    assert item_max_seq_length > 0, "Intro sentence exceeds max sequence length"
    chunks = [
        intro_sentence + some_list_items
        for some_list_items in _join_up_to_max_seq_length(
            list_items, item_max_seq_length, delimiter=join_delimiter
        )
    ]
    assert all(len(tokenize(chunk)) <= token_limit for chunk in chunks)
    return chunks


def _ensure_blank_line_suffix(text: str) -> str:
    "Return text with a blank line after the text"
    if not text.endswith("\n\n"):
        if text.endswith("\n"):
            text += "\n"
        else:
            text += "\n\n"
    return text


def deconstruct_table(
    markdown: str, has_intro_sentence: bool = False, list_delimiter: str = r"^(\| )"
) -> tuple[str, str, list[str]]:
    "Deconstruct a table of items into an introductory sentence, a table header, and a list of items"
    intro_sentence, list_items = deconstruct_list(markdown, has_intro_sentence, list_delimiter)

    if list_items[1].startswith("| --- |"):
        table_header = list_items.pop(0) + list_items.pop(0)
    else:  # Assume no table header
        table_header = ""

    return intro_sentence, table_header, list_items


def reconstruct_table(
    token_limit: int,
    intro_sentence: str,
    table_header: str,
    table_rows: Sequence[str],
    join_delimiter: str = "",
) -> list[str]:
    "Reconstruct a table of items into chunks (with intro_sentence + table_header) having up to a character limit each."

    # Before the table, there should be a blank line
    intro_sentence = _ensure_blank_line_suffix(intro_sentence)

    intro = intro_sentence + table_header
    item_max_seq_length = token_limit - len(tokenize(intro))
    assert item_max_seq_length > 0, item_max_seq_length
    print("item_max_seq_length", item_max_seq_length)
    for row in table_rows:
        print("row", row)
    chunks = [
        intro + some_table_rows
        for some_table_rows in _join_up_to_max_seq_length(
            table_rows, item_max_seq_length, delimiter=join_delimiter
        )
    ]
    assert all(len(tokenize(chunk)) <= token_limit for chunk in chunks)
    return chunks


def _join_up_to_max_seq_length(
    lines: Sequence[str], max_seq_length: int, delimiter: str = " "
) -> list[str]:
    chunks = []
    chunk = ""
    for line in lines:
        test_chunk = delimiter.join([chunk, line]) if chunk else line
        token_count = len(tokenize(test_chunk))
        logger.debug("%i / %i : %r", token_count, max_seq_length, test_chunk)
        if token_count > max_seq_length:
            # Don't use test_chunk; add current chunk; start a new chunk
            if chunk:
                chunks.append(chunk)

            line_token_count = len(tokenize(line))
            assert line_token_count <= max_seq_length, "Line is too long (%i tokens): %s" % (
                line_token_count,
                line,
            )
            chunk = line
        else:
            chunk = test_chunk

    # Add the last chunk
    chunks.append(chunk)

    assert all(len(tokenize(chunk)) <= max_seq_length for chunk in chunks)
    return chunks

import argparse
import inspect
import json
import logging
import os
import re
from logging import Logger
from pathlib import Path
from typing import Callable, Optional, Sequence

from smart_open import open as smart_open
from sqlalchemy import and_, delete, select
from sqlalchemy.sql import exists

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import ChunkingConfig

logger = logging.getLogger(__name__)


def _drop_existing_dataset(db_session: db.Session, dataset: str) -> bool:
    dataset_exists = db_session.execute(select(Document).where(Document.dataset == dataset)).first()
    if dataset_exists:
        db_session.execute(delete(Document).where(Document.dataset == dataset))
    return dataset_exists is not None


def document_exists(db_session: db.Session, url: str, doc_attribs: dict[str, str]) -> bool:
    # Existing documents are determined by the source URL; could use document.content instead
    if db_session.query(
        exists().where(
            and_(
                Document.source == url,
                Document.dataset == doc_attribs["dataset"],
                Document.program == doc_attribs["program"],
                Document.region == doc_attribs["region"],
            )
        )
    ).scalar():
        return True
    return False


def process_and_ingest_sys_args(argv: list[str], logger: Logger, ingestion_call: Callable) -> None:
    """Method that reads sys args and passes them into ingestion call"""

    # Print INFO messages since this is often run from the terminal during local development
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_id")
    parser.add_argument("benefit_program")
    parser.add_argument("benefit_region")
    parser.add_argument("file_path")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip_db", action="store_true")
    args = parser.parse_args(argv[1:])

    params = inspect.signature(ingestion_call).parameters
    if args.resume:
        if "resume" not in params:
            raise NotImplementedError(
                f"Ingestion function does not support `resume`: {ingestion_call}"
            )
        logger.info("Enabled resuming from previous run.")
    if args.skip_db:
        if "skip_db" not in params:
            raise NotImplementedError(
                f"Ingestion function does not support `skip_db`: {ingestion_call}"
            )
        logger.info("Skipping reading or writing to the DB.")

    doc_attribs = {
        "dataset": args.dataset_id,
        "program": args.benefit_program,
        "region": args.benefit_region,
    }
    logger.info("Ingesting from %s: %r", args.file_path, doc_attribs)

    with app_config.db_session() as db_session:
        if args.resume:
            ingestion_call(
                db_session, args.file_path, doc_attribs, skip_db=args.skip_db, resume=args.resume
            )
        else:
            dropped = _drop_existing_dataset(db_session, args.dataset_id)
            if dropped:
                logger.warning("Dropped existing dataset %s", args.dataset_id)
            db_session.commit()
            ingestion_call(db_session, args.file_path, doc_attribs, skip_db=args.skip_db)
        db_session.commit()

    logger.info("Finished ingesting")


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

    assert len(to_encode) > 0
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


def create_file_path(base_dir: str, common_base_url: str, source_url: str) -> str:
    assert common_base_url.endswith("/")
    relative_path = source_url.removeprefix(common_base_url)
    assert not relative_path.startswith("/")
    file_path = os.path.join(base_dir, relative_path)

    if file_path == "" or file_path.endswith("/"):
        # Ensure that the file_path ends with a filename
        file_path += "_index"
    return file_path


def load_or_save_doc_markdown(file_path: str, document: Document) -> str:
    md_file_path = f"{file_path}.md"
    if os.path.exists(md_file_path):
        # Load the markdown content from the file in case it's been manually edited
        logger.info("  Loading markdown from file: %r", md_file_path)
        document.content = Path(md_file_path).read_text(encoding="utf-8")
    else:
        logger.info("  Saving markdown to %r", md_file_path)
        assert document.content
        os.makedirs(os.path.dirname(md_file_path), exist_ok=True)
        Path(md_file_path).write_text(document.content, encoding="utf-8")
    return file_path


def save_json(file_path: str, chunks: list[Chunk]) -> None:
    chunks_as_json = [chunk.to_json() for chunk in chunks]
    with smart_open(file_path, "w") as file:
        file.write(json.dumps(chunks_as_json))

    # Save prettified chunks to a markdown file for manual inspection
    with smart_open(f"{os.path.splitext(file_path)[0]}.md", "w", encoding="utf-8") as file:
        file.write(f"{len(chunks)} chunks\n")
        file.write("\n")
        for chunk in chunks:
            if not chunk.tokens:
                chunk.tokens = len(tokenize(chunk.content))

            file.write(f"---\nlength:   {chunk.tokens}\nheadings: {chunk.headings}\n---\n")
            file.write(chunk.content)
            file.write("\n====================================\n")
        file.write("\n\n")


class DefaultChunkingConfig(ChunkingConfig):
    def __init__(self) -> None:
        super().__init__(app_config.sentence_transformer.max_seq_length)

    def text_length(self, text: str) -> int:
        return len(tokenize(text))

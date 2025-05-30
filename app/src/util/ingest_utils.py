import argparse
import inspect
import json
import logging
import os
from logging import Logger
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Sequence

from smart_open import open as smart_open
from sqlalchemy import and_, delete, select
from sqlalchemy.sql import exists

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import ChunkingConfig

logger = logging.getLogger(__name__)


def drop_existing_dataset(db_session: db.Session, dataset: str) -> bool:
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


class IngestConfig(NamedTuple):
    dataset_label: str
    benefit_program: str
    benefit_region: str
    common_base_url: str
    scraper_dataset: str
    prep_json_item: Optional[Callable[[dict[str, str]], None]] = None
    chunking_config: Optional[ChunkingConfig] = None

    @property
    def md_base_dir(self) -> str:
        return f"{self.scraper_dataset}_md"

    @property
    def doc_attribs(self) -> dict[str, str]:
        return {
            "dataset": self.dataset_label,
            "program": self.benefit_program,
            "region": self.benefit_region,
        }


def process_and_ingest_sys_args(
    argv: list[str],
    logger: Logger,
    ingestion_call: Callable,
    default_config: IngestConfig,
) -> None:
    """Method that reads sys args and passes them into ingestion call"""
    logger.info("Running with args: %r", argv)

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

    ingest_config = IngestConfig(
        args.dataset_id,
        args.benefit_program,
        args.benefit_region,
        default_config.common_base_url,
        default_config.scraper_dataset,
    )

    start_ingestion(
        logger,
        ingestion_call,
        args.file_path,
        ingest_config,
        skip_db=args.skip_db,
        resume=args.resume,
    )


def start_ingestion(
    logger: Logger,
    ingestion_call: Callable,
    file_path: str,
    config: IngestConfig,
    *,
    skip_db: bool = False,
    resume: bool = False,
) -> None:
    logger.info("Ingesting from %r: %r", file_path, config.doc_attribs)
    with app_config.db_session() as db_session:
        if resume:
            ingestion_call(db_session, file_path, config, skip_db=skip_db, resume=resume)
        else:
            if not skip_db:
                dropped = drop_existing_dataset(db_session, config.dataset_label)
                if dropped:
                    logger.warning("Dropped existing dataset %s", config.dataset_label)
                db_session.commit()
            ingestion_call(db_session, file_path, config, skip_db=skip_db)
        db_session.commit()
    logger.info("Finished ingesting %r (%s)", config.dataset_label, config.scraper_dataset)


def add_embeddings(
    chunks: Sequence[Chunk], texts_to_encode: Optional[Sequence[str]] = None
) -> None:
    """
    Add embeddings to each chunk using the text from either texts_to_encode or chunk.content.
    Arguments chunks and texts_to_encode should be the same length, or texts_to_encode can be None/empty.
    This allows us to create embeddings using text other than chunk.content.
    If the corresponding texts_to_encode element evaluates to False, then chunk.content is used instead.
    """
    embedding_model = app_config.embedding_model

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
        chunk.mpnet_embedding = embedding  # type: ignore
        token_len = embedding_model.token_length(text)
        if not chunk.tokens:
            chunk.tokens = token_len
        else:
            assert chunk.tokens == token_len, f"Token count mismatch: {chunk.tokens} != {token_len}"
        assert (
            chunk.tokens <= embedding_model.max_seq_length
        ), f"Text too long for embedding model: {chunk.tokens} tokens: {len(chunk.content)} chars: {chunk.content[:80]}...{chunk.content[-50:]}"


def create_file_path(base_dir: str, common_base_url: str, source_url: str) -> str:
    assert common_base_url.endswith("/")
    relative_path = source_url.removeprefix(common_base_url)
    assert not relative_path.startswith("/")
    file_path = os.path.join(base_dir, relative_path)

    if file_path == "" or file_path.endswith("/"):
        # Ensure that the file_path ends with a filename
        file_path += "_index"
    return file_path


def load_or_save_doc_markdown(file_path: str, content: str) -> str:
    md_file_path = f"{file_path}.md"
    if os.path.exists(md_file_path):
        # Load the markdown content from the file in case it's been manually edited
        logger.info("  Loading markdown from file instead: %r", md_file_path)
        content = Path(md_file_path).read_text(encoding="utf-8")
    else:
        logger.info("  Saving markdown to %r", md_file_path)
        assert content
        os.makedirs(os.path.dirname(md_file_path), exist_ok=True)
        Path(md_file_path).write_text(content, encoding="utf-8")
    return content


def save_json(file_path: str, chunks: list[Chunk]) -> None:
    chunks_as_json = [chunk.to_json() for chunk in chunks]
    with smart_open(file_path, "w", encoding="utf-8") as file:
        file.write(json.dumps(chunks_as_json))

    # Save prettified chunks to a markdown file for manual inspection
    with smart_open(f"{os.path.splitext(file_path)[0]}.md", "w", encoding="utf-8") as file:
        file.write(f"{len(chunks)} chunks\n")
        file.write("\n")
        for chunk in chunks:
            if not chunk.tokens:
                chunk.tokens = app_config.embedding_model.token_length(chunk.content)

            file.write(f"---\nlength:   {chunk.tokens}\nheadings: {chunk.headings}\n---\n")
            file.write(chunk.content)
            file.write("\n====================================\n")
        file.write("\n\n")


class DefaultChunkingConfig(ChunkingConfig):
    def __init__(self) -> None:
        super().__init__(app_config.embedding_model.max_seq_length)

    def text_length(self, text: str) -> int:
        return app_config.embedding_model.token_length(text)

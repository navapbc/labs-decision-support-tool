import json
import logging
import os
import re
import sys
from typing import Optional, Sequence

from nutree import Tree
from smart_open import open as smart_open
from sqlalchemy import and_
from sqlalchemy.sql import exists

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import ChunkingConfig, chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.util.ingest_utils import (
    add_embeddings,
    process_and_ingest_sys_args,
    tokenize,
)
from src.util.string_utils import remove_links

logger = logging.getLogger(__name__)


def _item_exists(db_session: db.Session, item: dict[str, str], doc_attribs: dict[str, str]) -> bool:
    # Existing documents are determined by the source URL; could use document.content instead
    if db_session.query(
        exists().where(
            and_(
                Document.source == item["url"],
                Document.dataset == doc_attribs["dataset"],
                Document.program == doc_attribs["program"],
                Document.region == doc_attribs["region"],
            )
        )
    ).scalar():
        logger.info("Skipping -- item already exists: %r", item["url"])
        return True
    return False


def _ingest_la_county_policy(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
    resume: bool = False,
) -> None:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    if resume:
        json_items = [
            item for item in json_items if not _item_exists(db_session, item, doc_attribs)
        ]

    # First, split all json_items into chunks (fast) to debug any issues quickly
    all_chunks = _create_chunks(json_items, doc_attribs)
    logger.info(
        "Done splitting %d webpages into %d chunks",
        len(json_items),
        sum(len(chunks) for _, chunks, _ in all_chunks),
    )
    for document, chunks, splits in all_chunks:
        if not chunks:
            logger.warning("No chunks for %r", document.source)
            continue

        logger.info("Adding embeddings for %r", document.source)
        # Next, add embeddings to each chunk (slow)
        add_embeddings(chunks, [s.text_to_encode for s in splits])
        logger.info("Embedded webpage across %d chunks: %r", len(chunks), document.name)

        # Then, add to the database
        db_session.add(document)
        db_session.add_all(chunks)
        if resume:
            db_session.commit()


class SplitWithContextText:

    def __init__(
        self,
        headings: Sequence[str],
        text: str,
        context_str: str,
        text_to_encode: Optional[str] = None,
    ):
        self.headings = headings
        self.text = text
        if text_to_encode:
            self.text_to_encode = text_to_encode
        else:
            self.text_to_encode = f"{context_str.strip()}\n\n" + remove_links(text)
        self.token_count = len(tokenize(self.text_to_encode))
        self.chunk_id = ""
        self.data_ids = ""

    def add_if_within_limit(self, paragraph: str, delimiter: str = "\n\n") -> bool:
        new_text_to_encode = f"{self.text_to_encode}{delimiter}{remove_links(paragraph)}"
        token_count = len(tokenize(new_text_to_encode))
        if token_count <= app_config.sentence_transformer.max_seq_length:
            self.text += f"{delimiter}{paragraph}"
            self.text_to_encode = new_text_to_encode
            self.token_count = token_count
            return True
        return False

    def exceeds_limit(self) -> bool:
        if self.token_count > app_config.sentence_transformer.max_seq_length:
            logger.warning("Text too long! %i tokens: %s", self.token_count, self.text_to_encode)
            return True
        return False


def _create_chunks(
    json_items: Sequence[dict[str, str]],
    doc_attribs: dict[str, str],
) -> Sequence[tuple[Document, Sequence[Chunk], Sequence[SplitWithContextText]]]:
    urls_processed: set[str] = set()
    result = []
    for item in json_items:
        if item["url"] in urls_processed:
            # Workaround for duplicate items from web scraping
            logger.warning("Skipping duplicate URL: %s", item["url"])
            continue

        logger.info("Processing: %s", item["url"])
        urls_processed.add(item["url"])

        content = item.get("markdown", None)
        assert content, f"Item {item['url']} has no markdown content"

        title = item["h2"]  # More often than not, the h2 heading is better suited as the title
        document = Document(name=title, content=content, source=item["url"], **doc_attribs)
        chunks, splits = _chunk_page(document, content)
        logger.info("Split into %d chunks: %s", len(chunks), title)
        result.append((document, chunks, splits))
    return result


USE_MARKDOWN_TREE = True


def _chunk_page(
    document: Document, content: str
) -> tuple[Sequence[Chunk], Sequence[SplitWithContextText]]:
    splits = _create_splits_using_markdown_tree(content, document)

    chunks = [
        Chunk(
            document=document,
            content=split.text,
            headings=split.headings,
            num_splits=len(splits),
            split_index=index,
            tokens=split.token_count,
        )
        for index, split in enumerate(splits)
    ]
    return chunks, splits


class EddChunkingConfig(ChunkingConfig):
    def __init__(self) -> None:
        super().__init__(app_config.sentence_transformer.max_seq_length)

    def text_length(self, text: str) -> int:
        return len(tokenize(text))


def _create_splits_using_markdown_tree(
    content: str, document: Document
) -> list[SplitWithContextText]:
    splits: list[SplitWithContextText] = []
    chunking_config = EddChunkingConfig()
    content = _fix_input_markdown(content)
    try:
        tree = create_markdown_tree(content, doc_name=document.name, doc_source=document.source)
        tree_chunks = chunk_tree(tree, chunking_config)

        for chunk in tree_chunks:
            split = SplitWithContextText(
                chunk.headings, chunk.markdown, chunk.context_str, chunk.embedding_str
            )
            assert split.token_count == chunk.length
            splits.append(split)
            if os.path.exists("SAVE_CHUNKS"):
                # Add some extra info for debugging
                split.chunk_id = chunk.id
                split.data_ids = ", ".join(chunk.data_ids)
        if os.path.exists("SAVE_CHUNKS"):
            assert document.source
            _save_splits_to_files(document.source, content, splits, tree)
    except (Exception, KeyboardInterrupt) as e:  # pragma: no cover
        logger.error("Error chunking %s (%s): %s", document.name, document.source, e)
        logger.error(tree.format())
        raise e
    return splits


def _fix_input_markdown(markdown: str) -> str:
    return markdown


def _save_splits_to_files(
    uri: str, content: str, splits: list[SplitWithContextText], tree: Tree
) -> None:  # pragma: no cover
    url_path = "chunks-log/" + uri.removeprefix("https://edd.ca.gov/en/").rstrip("/")
    os.makedirs(os.path.dirname(url_path), exist_ok=True)
    with open(f"{url_path}.json", "w", encoding="utf-8") as file:
        file.write(f"{uri} => {len(splits)} chunks\n")
        file.write("\n")
        for split in splits:
            file.write(f">>> {split.chunk_id!r} (length {split.token_count}) {split.headings}\n")
            file.write(split.text)
            file.write("\n--------------------------------------------------\n")
        file.write("\n\n")
        json_str = json.dumps([split.__dict__ for split in splits], indent=2)
        file.write(json_str)
        file.write("\n\n")
        file.write(tree.format())
        file.write("\n\n")
        file.write(content)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_la_county_policy)

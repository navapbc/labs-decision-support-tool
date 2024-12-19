import json
import logging
import sys
from typing import Sequence

from smart_open import open as smart_open

from src.adapters import db
from src.db.models.document import Chunk, Document
from src.util.ingest_utils import (
    add_embeddings,
    document_exists,
    process_and_ingest_sys_args,
)
from src.ingest_edd_web import SplitWithContextText, _create_splits_using_markdown_tree

logger = logging.getLogger(__name__)


common_base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/mergedProjects/"


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
            item for item in json_items if not document_exists(db_session, item["url"], doc_attribs)
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
    splits = _create_splits_using_markdown_tree(content, document, common_base_url)

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


def _fix_input_markdown(markdown: str) -> str:
    "Placeholder hook for fixing input markdown"
    return markdown


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_la_county_policy)

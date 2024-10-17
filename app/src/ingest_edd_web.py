import json
import logging
import sys

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.ingest_utils import process_and_ingest_sys_args, tokenize

logger = logging.getLogger(__name__)


def _ingest_edd_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
) -> None:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    urls_processed: set[str] = set()
    for item in json_items:
        if item["url"] in urls_processed:
            # Workaround for duplicate items from web scraping
            logger.warning("Skipping duplicate URL: %s", item["url"])
            continue

        name = item["title"]
        logger.info("Processing %s (%s)", name, item["url"])
        urls_processed.add(item["url"])

        content = item.get("main_content", item.get("main_primary"))
        assert content, f"Item {name} has no main_content or main_primary"

        document = Document(name=name, content=content, source=item["url"], **doc_attribs)
        db_session.add(document)

        chunks = _chunk_page(content)
        for chunk in chunks:
            chunk.document = document
        db_session.add_all(chunks)
        logger.info("Split %s into %d chunks", name, len(chunks))


def _chunk_page(content: str) -> list[Chunk]:
    embedding_model = app_config.sentence_transformer

    # Split content by double newlines, then gather into the largest chunks
    # that tokenize to less than the max_seq_length
    content_split_by_double_newlines = content.split("\n\n")
    subsections = [content_split_by_double_newlines[0]]
    for subsection in content_split_by_double_newlines[1:]:
        tokens_with_new_subsection = len(tokenize(subsections[-1] + subsection))
        if tokens_with_new_subsection < embedding_model.max_seq_length:
            subsections[-1] += "\n\n" + subsection
        else:
            subsections.append(subsection)

    # Parallelize embedding generation for performance
    subsection_embeddings = embedding_model.encode(subsections, show_progress_bar=False)

    return [
        Chunk(
            content=subsection,
            mpnet_embedding=embedding,
            tokens=len(tokenize(subsection)),
        )
        for subsection, embedding in zip(subsections, subsection_embeddings, strict=True)
    ]


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)

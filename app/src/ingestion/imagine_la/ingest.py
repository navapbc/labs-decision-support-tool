import logging
import sys
from typing import Optional, Sequence

from bs4 import BeautifulSoup
from bs4.element import PageElement
from markdownify import markdownify
from smart_open import open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import ChunkingConfig, chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.util.file_util import get_files
from src.util.ingest_utils import (
    IngestConfig,
    add_embeddings,
    create_file_path,
    load_or_save_doc_markdown,
    process_and_ingest_sys_args,
    save_json,
)

logger = logging.getLogger(__name__)


class ImagineLaChunkingConfig(ChunkingConfig):
    def __init__(self) -> None:
        super().__init__(app_config.embedding_model.max_seq_length)

    def text_length(self, text: str) -> int:
        return app_config.embedding_model.token_length(text)


def _parse_html(
    md_base_dir: str, common_base_url: str, file_path: str, doc_attribs: dict[str, str]
) -> tuple[Document, Sequence[Chunk], Sequence[str]]:

    logger.info("Reading %r", file_path)
    with open(file_path, "r") as file:
        file_contents = file.read()
    soup = BeautifulSoup(file_contents, "html.parser")

    h1 = soup.find("h1")
    assert isinstance(h1, PageElement)
    doc_attribs["name"] = h1.text.strip()
    # Get filename and strip ".html" to get the source URL
    doc_attribs["source"] = common_base_url + file_path.split("/")[-1][:-5]
    document = Document(**doc_attribs)

    content = markdownify(
        file_contents,
        heading_style="ATX",
    )

    assert document.source
    file_path = create_file_path(md_base_dir, common_base_url, document.source)
    document.content = load_or_save_doc_markdown(file_path, content)

    # Convert markdown to chunks
    tree = create_markdown_tree(content, doc_name=document.name, doc_source=document.source)
    tree_chunks = chunk_tree(tree, ImagineLaChunkingConfig())
    chunks = [
        Chunk(
            content=chunk.markdown, document=document, headings=chunk.headings, tokens=chunk.length
        )
        for chunk in tree_chunks
    ]
    chunk_texts_to_encode = [t_chunk.embedding_str for t_chunk in tree_chunks]

    chunks_file_path = f"{file_path}.chunks.json"
    logger.info("  Saving chunks to %r", chunks_file_path)
    save_json(chunks_file_path, chunks)

    return document, chunks, chunk_texts_to_encode


def _ingest_content_hub(
    db_session: db.Session,
    html_file_dir: str,
    config: IngestConfig,
    *,
    skip_db: bool = False,
    md_base_dir: Optional[str] = None,
) -> None:
    file_list = sorted(get_files(html_file_dir))

    logger.info(
        "Processing HTML files in %s using %s with %s",
        html_file_dir,
        app_config.embedding_model,
        config.doc_attribs,
    )

    all_chunks: list[tuple[Document, Sequence[Chunk], Sequence[str]]] = []
    for file_path in file_list:
        if not file_path.endswith(".html"):
            continue

        logger.info("Processing file: %s", file_path)
        result = _parse_html(
            md_base_dir or config.md_base_dir, config.common_base_url, file_path, config.doc_attribs
        )
        all_chunks.append(result)

    logger.info(
        "=== DONE splitting all %d webpages into a total of %d chunks",
        len(all_chunks),
        sum(len(chunks) for _, chunks, _ in all_chunks),
    )

    if skip_db:
        logger.info("Skip saving to DB")
    else:
        for document, chunks, chunk_texts_to_encode in all_chunks:
            logger.info("Adding embeddings for %r", document.source)
            add_embeddings(chunks, chunk_texts_to_encode)
            db_session.add(document)
            db_session.add_all(chunks)


def main() -> None:
    # Print INFO messages since this is often run from the terminal during local development
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    default_config = IngestConfig(
        "Benefits Information Hub",
        "mixed",
        "California",
        "https://benefitnavigator.web.app/contenthub/",
        "imagine_la",
    )
    process_and_ingest_sys_args(sys.argv, logger, _ingest_content_hub, default_config)

import logging
import sys
from typing import BinaryIO

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from smart_open import open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.markdown_chunking import ChunkingConfig, chunk_tree
from src.ingestion.markdown_tree import create_markdown_tree
from src.util.file_util import get_files
from src.util.ingest_utils import add_embeddings, process_and_ingest_sys_args, save_json, tokenize
from src.util.string_utils import remove_links

logger = logging.getLogger(__name__)


CONTENT_HUB_URL = "https://socialbenefitsnavigator25.web.app/contenthub/"


class ImagineLaChunkingConfig(ChunkingConfig):
    def __init__(self) -> None:
        super().__init__(app_config.sentence_transformer.max_seq_length)

    def text_length(self, text: str) -> int:
        return len(tokenize(text))


def _parse_html(
    file: BinaryIO, file_path: str, doc_attribs: dict[str, str]
) -> tuple[Document, list[Chunk], list[str]]:

    file_contents = file.read()
    soup = BeautifulSoup(file_contents, "html.parser")

    doc_attribs["name"] = soup.find("h2").text.strip()
    # Get filename and strip ".html" to get the source URL
    doc_attribs["source"] = CONTENT_HUB_URL + file_path.split("/")[-1][:-5]
    document = Document(**doc_attribs)

    # Extract accordions
    accordion_data: dict[str, str] = {}
    for item in soup.find_all("div", class_="chakra-accordion__item"):
        heading_button = item.find("button", class_="chakra-accordion__button")
        heading = (
            heading_button.find("p", class_="chakra-text").text.strip() if heading_button else None
        )

        body_div = item.find("div", class_="chakra-collapse")
        body_html = body_div.decode_contents() if body_div else None

        if heading and body_html:
            accordion_data[heading] = body_html

    # Convert to markdown
    content = f"# {document.name}\n\n"
    for heading, body in accordion_data.items():
        content += f"## {heading}\n\n{md(body)}\n\n"
    document.content = content

    # Convert markdown to chunks
    tree = create_markdown_tree(content, doc_name=document.name, doc_source=document.source)
    tree_chunks = chunk_tree(tree, ImagineLaChunkingConfig())
    chunks = [
        Chunk(content=chunk.markdown, document=document, headings=chunk.headings)
        for chunk in tree_chunks
    ]
    chunk_texts_to_encode = [remove_links(chunk.markdown) for chunk in tree_chunks]

    return document, chunks, chunk_texts_to_encode


def _ingest_content_hub(
    db_session: db.Session,
    html_file_dir: str,
    doc_attribs: dict[str, str],
    should_save_json: bool = True,
) -> None:
    file_list = sorted(get_files(html_file_dir))

    logger.info(
        "Processing HTML files in %s using %s with %s",
        html_file_dir,
        app_config.embedding_model,
        doc_attribs,
    )
    for file_path in file_list:
        if not file_path.endswith(".html"):
            continue

        logger.info("Processing file: %s", file_path)
        with open(file_path, "r") as file:
            document, chunks, chunk_texts_to_encode = _parse_html(file, file_path, doc_attribs)
            add_embeddings(chunks, chunk_texts_to_encode)
            db_session.add(document)
            db_session.add_all(chunks)
            if should_save_json:
                save_json(file_path, chunks)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_content_hub)

import logging
import sys
import uuid
from dataclasses import dataclass
from typing import BinaryIO

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.pdf_elements import EnrichedText
from src.ingestion.pdf_postprocess import add_markdown, group_texts
from src.util import pdf_utils
from src.util.file_util import get_files
from src.util.ingest_utils import process_and_ingest_sys_args
from src.util.pdf_utils import Heading

logger = logging.getLogger(__name__)

# Print INFO messages since this is often run from the terminal
# during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _get_bem_title(file: BinaryIO, file_path: str) -> str:
    """
    Get the BEM number from the file path (e.g., 100.pdf) and the
    document title from the PDF meta data, then put the document
    title in title case (e.g., INTRODUCTION EXAMPLE -> Introduction Example)
    and combine: "BEM 100: Introduction Example"
    """
    pdf_info = pdf_utils.get_pdf_info(file)
    pdf_title = pdf_info.title or file_path
    bem_num = file_path.split("/")[-1].rsplit(".", 1)[0]
    return f"BEM {bem_num}: {pdf_title}"


def _ingest_bem_pdfs(
    db_session: db.Session,
    pdf_file_dir: str,
    doc_attribs: dict[str, str],
) -> None:
    file_list = get_files(pdf_file_dir)

    logger.info(
        "Processing PDFs in %s using %s with %s",
        pdf_file_dir,
        app_config.embedding_model,
        doc_attribs,
    )
    for file_path in file_list:
        if not file_path.endswith(".pdf"):
            continue

        logger.info("Processing file: %s", file_path)
        with smart_open(file_path, "rb") as file:
            grouped_texts = _parse_pdf(file)

            doc_attribs["name"] = _get_bem_title(file, file_path)
            document = Document(content="\n".join(g.text for g in grouped_texts), **doc_attribs)
            db_session.add(document)
            chunks = split_into_chunks(document, grouped_texts)
            for chunk in chunks:
                _add_chunk(db_session, chunk.content, chunk.document, chunk.tokens)


def _parse_pdf(file: BinaryIO) -> list[EnrichedText]:
    enriched_texts = enrich_texts(file)
    markdown_texts = add_markdown(enriched_texts)
    grouped_texts = group_texts(markdown_texts)

    # Assign unique ids to each grouped text before they get split into chunks
    for text in grouped_texts:
        text.id = str(uuid.uuid1())
    assert len(set(text.id for text in grouped_texts)) == len(grouped_texts)
    return grouped_texts


def enrich_texts(file: BinaryIO) -> list[EnrichedText]:
    "Placeholder function. Will be implemented for DST-414, probably in a different file."
    outline: list[Heading] = pdf_utils.extract_outline(file)
    for _heading in outline:
        pass
    return []


def split_into_chunks(document: Document, grouped_texts: list[EnrichedText]) -> list[Chunk]:
    """
    Given EnrichedTexts, convert the text to chunks and add them to the database.
    """
    chunks: list[Chunk] = []
    for paragraph in grouped_texts:
        assert paragraph.id is not None
        assert paragraph.page_number is not None

        # For iteration 1, log warning for overly long text
        embedding_model = app_config.sentence_transformer
        token_count = len(embedding_model.tokenizer.tokenize(paragraph))
        if token_count > embedding_model.max_seq_length:
            logger.warning("Text too long for embedding model: %s", paragraph.text[:100])

        text_chunks = [
            # For iteration 1, don't split the text -- just create 1 chunk.
            # TODO: TASK 3.a will split a paragraph into multiple chunks.
            Chunk(
                content=paragraph.text,
                tokens=len(paragraph.text.split()),
                document=document,
                text_type=paragraph.type.name,
                page_number=paragraph.page_number,
                headings=[h.title for h in paragraph.headings],
                num_splits=1,
            )
        ]
        chunks += text_chunks
    return chunks


def _add_chunk(
    db_session: db.Session, chunk_text: str, document: Document, current_token_count: int
) -> None:
    embedding_model = app_config.sentence_transformer
    chunk_embedding = embedding_model.encode(chunk_text, show_progress_bar=False)
    chunk = Chunk(
        document=document,
        content=chunk_text,
        tokens=current_token_count,
        mpnet_embedding=chunk_embedding,
    )
    db_session.add(chunk)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_bem_pdfs)

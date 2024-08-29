import logging
import re
import sys
import uuid
from typing import Any, BinaryIO

import nltk
from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.pdf_elements import EnrichedText
from src.ingestion.pdf_postprocess import add_markdown, associate_stylings, group_texts
from src.ingestion.pdf_stylings import extract_stylings
from src.util import pdf_utils
from src.util.file_util import get_files
from src.util.ingest_utils import process_and_ingest_sys_args
from src.util.pdf_utils import Heading
from src.util.unstructured_utils import get_json_from_file

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
    nltk.download("punkt_tab")
    nltk.download("averaged_perceptron_tagger_eng")

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
            grouped_texts = _parse_pdf(file, file_path)

            doc_attribs["name"] = _get_bem_title(file, file_path)
            document = Document(content="\n".join(g.text for g in grouped_texts), **doc_attribs)
            db_session.add(document)
            chunks = split_into_chunks(document, grouped_texts)
            for chunk in chunks:
                _add_chunk(db_session, chunk)


def _parse_pdf(file: BinaryIO) -> list[EnrichedText]:
    unstructured_json = get_json_from_file(file)
    enriched_texts = enrich_texts(file, unstructured_json)
    stylings = extract_stylings(file)
    associate_stylings(enriched_texts, stylings)
    markdown_texts = add_markdown(enriched_texts)
    grouped_texts = group_texts(markdown_texts)

    # Assign unique ids to each grouped text before they get split into chunks
    for text in grouped_texts:
        text.id = str(uuid.uuid1())
    assert len(set(text.id for text in grouped_texts)) == len(grouped_texts)

    return grouped_texts


def enrich_texts(file: BinaryIO, unstructured_json: list[dict[str, Any]]) -> list[EnrichedText]:
    enrich_text_list = []
    "Placeholder function. Will be implemented for DST-414, probably in a different file."
    outline: list[Heading] = pdf_utils.extract_outline(file)
    current_header = []
    current_header_level = 1
    for element in unstructured_json:
        if element["type"] == "Header" or element["type"] == "Footer":
            continue
        if element["type"] == "Title":
            header = match_heading(outline, element["text"], element["metadata"]["page_number"])
            if header:
                if header.level == 1:
                    current_header = [header]
                    current_header_level = 1
                else:
                    if header.title != current_header[-1]:
                        if current_header_level == header.level:
                            current_header = current_header[:-1]
                        if header.level > current_header_level:
                            current_header_level = header.level
                        current_header.append(header)

        # Unstructured fails to categorize the date strings in the header,
        # so manually check for that and ignore those too
        if element["type"] == "UncategorizedText" and re.match(
            r"^\d{1,2}-\d{1,2}-\d{4}$", element["text"]
        ):
            continue

        enriched_text_item = EnrichedText(
            text=element["text"],
            type=element["type"],
            page_number=element["metadata"]["page_number"],
            headings=current_header,
            id=element["element_id"],
        )

        enrich_text_list.append(enriched_text_item)
    return enrich_text_list


def match_heading(
    heading_list: list[Heading], heading_name: str, page_number: int
) -> Heading | None:
    for heading in heading_list:
        if heading_name.lower() in heading.title.lower() and heading.pageno == page_number:
            return heading
    return None


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
        token_count = len(embedding_model.tokenizer.tokenize(paragraph.text))
        if token_count > embedding_model.max_seq_length:
            logger.warning("Text too long for embedding model: %s", paragraph.text[:100])
        text_chunks = [
            # For iteration 1, don't split the text -- just create 1 chunk.
            # TODO: TASK 3.a will split a paragraph into multiple chunks.
            Chunk(
                content=paragraph.text,
                tokens=len(paragraph.text.split()),
                document=document,
                page_number=paragraph.page_number,
                headings=[h.title for h in paragraph.headings],
                num_splits=1,
            )
        ]
        chunks += text_chunks
    return chunks


def _add_chunk(
    db_session: db.Session,
    chunk: Chunk,
) -> None:
    embedding_model = app_config.sentence_transformer
    chunk_embedding = embedding_model.encode(chunk.content, show_progress_bar=False)
    chunk = Chunk(
        document=chunk.document,
        content=chunk.content,
        tokens=chunk.tokens,
        mpnet_embedding=chunk_embedding,
        page_number=chunk.page_number,
        headings=chunk.headings,
        num_splits=chunk.num_splits,
        split_index=chunk.split_index,
    )
    db_session.add(chunk)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_bem_pdfs)

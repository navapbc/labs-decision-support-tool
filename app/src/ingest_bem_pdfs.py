import logging
import re
import sys
import uuid
from typing import BinaryIO

from smart_open import open as smart_open
from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.ingestion.pdf_elements import EnrichedText, TextType
from src.ingestion.pdf_postprocess import add_markdown, associate_stylings, group_texts
from src.ingestion.pdf_stylings import extract_stylings
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
                _add_chunk(db_session, chunk)


def _parse_pdf(file: BinaryIO) -> list[EnrichedText]:
    enriched_texts = _enrich_texts(file)
    stylings = extract_stylings(file)
    associate_stylings(enriched_texts, stylings)
    markdown_texts = add_markdown(enriched_texts)
    grouped_texts = group_texts(markdown_texts)

    # Assign unique ids to each grouped text before they get split into chunks
    for text in grouped_texts:
        text.id = str(uuid.uuid1())
    assert len(set(text.id for text in grouped_texts)) == len(grouped_texts)

    return grouped_texts


def _enrich_texts(file: BinaryIO) -> list[EnrichedText]:
    unstuctured_elem_list = partition_pdf(file=file, strategy="fast")
    enrich_text_list = []

    outline: list[Heading] = pdf_utils.extract_outline(file)
    current_headings: list[Heading] = []
    for element in unstuctured_elem_list:
        if element.category == "Footer" or element.category == "Header":
            continue

        # Unstructured fails to categorize the date strings in the header,
        # so manually check for that and ignore those too
        if element.category == "UncategorizedText" and re.match(
            r"^\d{1,2}-\d{1,2}-\d{4}$", element.text
        ):
            continue

        if element.category == "Title":
            current_headings = _get_current_heading(outline, element, current_headings)
        try:
            enriched_text_item = EnrichedText(
                text=element.text,
                type=TextType(element.category),
                page_number=element.metadata.page_number,
                headings=current_headings,
                id=element._element_id,
            )
            enrich_text_list.append(enriched_text_item)
        except ValueError:
            logger.warning(
                f"{element.category} is not an accepted TextType, {element.text}, {element.metadata.page_number}"
            )
    return enrich_text_list


def _match_heading(
    outline: list[Heading], heading_name: str, page_number: int | None
) -> Heading | None:
    for heading in outline:
        if heading.pageno == page_number:
            # account for spacing differences in unstructured and pdfminer parsing
            heading_words = [word for word in heading.title.casefold() if not word.isspace()]
            element_words = [word for word in heading_name.casefold() if not word.isspace()]
            if heading_words == element_words:
                return heading
    return None


def _get_current_heading(
    outline: list[Heading], element: Element, current_headings: list[Heading]
) -> list[Heading]:
    if heading := _match_heading(outline, element.text, element.metadata.page_number):
        if heading.level == 1:
            current_headings = [heading]
        else:
            if heading.title != current_headings[-1].title:
                current_headings = current_headings[: -(heading.level - 1)]
                current_headings.append(heading)
    else:
        logger.warning(f"Unable to match header: {element.text}, {element.metadata.page_number}")
    return current_headings


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

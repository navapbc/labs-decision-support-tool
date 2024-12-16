import logging
import re
import sys

from pdfminer.high_level import extract_text
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from smart_open import open as smart_open_file

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.file_util import get_files
from src.util.ingest_utils import process_and_ingest_sys_args, tokenize

logger = logging.getLogger(__name__)


def _get_pdf_title(file_path: str) -> str:
    """
    Get the document title from the PDF metadata.
    If no title is found, use the filename without extension.
    """
    with smart_open_file(file_path, "rb") as file:
        try:
            pdf_title = PDFDocument(PDFParser(file)).info[0]["Title"].decode().title()
        except (KeyError, AttributeError):
            # If no title in metadata, use filename without extension
            pdf_title = file_path.split("/")[-1].rsplit(".", 1)[0]
    return pdf_title


def _ingest_policy_pdfs(
    db_session: db.Session,
    pdf_file_dir: str,
    doc_attribs: dict[str, str],
) -> None:
    file_list = get_files(pdf_file_dir)
    embedding_model = app_config.sentence_transformer

    logger.info(f"Processing pdfs {pdf_file_dir} using {embedding_model} with {doc_attribs}")
    for file_path in file_list:
        if file_path.endswith(".pdf"):
            logger.info(f"Processing pdf file: {file_path}")
            with smart_open_file(file_path, "rb") as file:
                output_string = extract_text(file)
                doc_attribs["name"] = _get_pdf_title(file_path)
                parse_pdf_and_add_to_db(
                    contents=output_string, doc_attribs=doc_attribs, db_session=db_session
                )


def parse_pdf_and_add_to_db(
    contents: str, doc_attribs: dict[str, str], db_session: db.Session
) -> None:
    document = Document(content=contents, **doc_attribs)
    db_session.add(document)

    process_chunk(contents, document, db_session)


def process_chunk(text: str, document: Document, db_session: db.Session) -> None:
    embedding_model = app_config.sentence_transformer
    sentence_boundary_pattern = r"(?<=[.!?])\s+(?=[^\d])"
    sentence_boundaries = [
        (m.start(), m.end()) for m in re.finditer(sentence_boundary_pattern, text)
    ]

    current_chunk = []
    current_token_count = 0
    current_position = 0

    for boundary_start, boundary_end in sentence_boundaries:
        sentence = text[current_position : boundary_start + 1]
        current_position = boundary_end

        token_count = len(tokenize(sentence))

        if current_token_count + token_count <= embedding_model.max_seq_length:
            current_chunk.append(sentence)
            current_token_count += token_count
        else:
            _add_chunk(db_session, current_chunk, document, current_token_count)
            # Initialize the variable with sentence, which was not used in the above chunk added to the DB
            current_chunk = [sentence]
            current_token_count = token_count

    # Append the last sentence
    last_sentence = text[current_position:]
    current_chunk.append(last_sentence)
    _add_chunk(db_session, current_chunk, document, current_token_count)


def _add_chunk(
    db_session: db.Session, current_chunk: list[str], document: Document, current_token_count: int
) -> None:
    embedding_model = app_config.sentence_transformer
    chunk_text = "".join(current_chunk)
    chunk_embedding = embedding_model.encode(chunk_text, show_progress_bar=False)
    chunk = Chunk(
        document=document,
        content=chunk_text,
        tokens=current_token_count,
        mpnet_embedding=chunk_embedding,
    )
    db_session.add(chunk)


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_policy_pdfs)

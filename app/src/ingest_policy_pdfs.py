import logging
import re
import sys
from io import StringIO

from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from sentence_transformers import SentenceTransformer
from smart_open import open as smart_open_file

import src.adapters.db as db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.file_util import get_files
from src.util.ingest_utils import process_and_ingest_sys_args

output_string = StringIO()

logger = logging.getLogger(__name__)

# Print INFO messages since this is often run from the terminal
# during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _ingest_policy_pdfs(
    db_session: db.Session,
    pdf_file_dir: str,
    doc_attribs: dict[str, str],
) -> None:
    file_list = get_files(pdf_file_dir)
    embedding_model = app_config.sentence_transformer
    for file in file_list:
        if file.endswith(".pdf"):
            with smart_open_file(file, "rb") as fin:
                extract_text_to_fp(
                    fin, output_string, laparams=LAParams(), output_type="text", codec=None
                )

                parse_pdf_and_add_to_db(
                    contents=output_string.getvalue(),
                    db_session=db_session,
                    doc_attribs=doc_attribs,
                    embedding_model=embedding_model,
                )

            logger.info(
                f"Processing pdf file: {file} at {pdf_file_dir} using {embedding_model}, {db_session}, with {doc_attribs}"
            )


def parse_pdf_and_add_to_db(
    contents: str,
    db_session: db.Session,
    doc_attribs: dict[str, str],
    embedding_model: SentenceTransformer,
) -> None:
    # Match header in BEM manual
    header_pattern = r"(BEM\s\d*\s+\d+\sof\s\d+\s+\w.*)"
    text_split_by_header = re.split(header_pattern, contents)
    current_title = ""
    body_content = ""
    start_new_section = True
    for text_contents in text_split_by_header:
        is_header, contents, start_new_section = get_header_and_is_current_section(
            text_contents, start_new_section
        )
        # Check if we need to start a new section
        if is_header and start_new_section and body_content != "":
            current_title = contents
        else:
            body_content += f"{contents}\n"

        # If starting a new section and body content is not empty, process and save it
        if start_new_section and body_content.strip():
            # Create and add the document to the database
            document = Document(name=current_title, content=body_content, **doc_attribs)
            db_session.add(document)

            # Tokenize and encode the content
            tokens = len(embedding_model.tokenizer.tokenize(body_content))
            mpnet_embedding = embedding_model.encode(body_content, show_progress_bar=False)

            # Create and add the chunk to the database
            chunk = Chunk(
                document=document,
                content=body_content,
                tokens=tokens,
                mpnet_embedding=mpnet_embedding,
            )
            db_session.add(chunk)

            # Check if token count exceeds the maximum sequence length
            if tokens > embedding_model.max_seq_length:
                logger.warning(
                    f"Page {current_title!r} has {tokens} tokens, which exceeds the embedding model's max sequence length."
                )

            # Reset the section state
            current_title = contents
            start_new_section = False
            body_content = ""


def get_header_and_is_current_section(line_contents, start_new_section):
    line_details = line_contents.split("\n\n")
    is_header = True
    if "BEM" in line_contents and "of" in line_contents and len(line_details) == 3:
        bem_val, page_num, title = line_details
        current_page, last_page = [x.strip() for x in page_num.split(" of ")]
        start_new_section = current_page == "1" or current_page == last_page
        title = f"{bem_val}: {title}".strip()
        contents = title
    else:
        is_header = False
        contents = line_contents

    return is_header, contents, start_new_section


def main() -> None:
    if len(sys.argv) < 5:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            sys.argv[1:],
        )
        return

    process_and_ingest_sys_args(sys, logger, _ingest_policy_pdfs)

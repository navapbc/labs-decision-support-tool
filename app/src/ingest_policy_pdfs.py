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
    # Splits by headers in text
    header_pattern = r"(BEM\s\d*\s+\d+\sof\s\d+\s+\w.*)"
    text_split_by_header = re.split(header_pattern, contents)
    content = ""
    title = ""
    last_section = False
    for ind, text_contents in enumerate(text_split_by_header):
        line_contents = get_header_and_is_current_section(text_contents)
        if len(line_contents) == 2:
            title, last_section = line_contents

        content += f"{text_contents}\n"

        if last_section:
            document = Document(name=title, content=content, **doc_attribs)
            db_session.add(document)
            tokens = len(embedding_model.tokenizer.tokenize(content))
            mpnet_embedding = embedding_model.encode(content, show_progress_bar=False)
            chunk = Chunk(
                document=document, content=content, tokens=tokens, mpnet_embedding=mpnet_embedding
            )
            db_session.add(chunk)

            if tokens > embedding_model.max_seq_length:
                logger.warning(
                    f"Page {title!r} has {tokens} tokens, which exceeds the embedding model's max sequence length."
                )
            last_section = False
            content = ""


def get_header_and_is_current_section(line_contents):
    line_details = line_contents.split("\n\n")
    if "BEM" in line_contents and "of" in line_contents and len(line_details) == 3:
        bem_val, page_num, title = line_details
        current_page, last_page = [x.strip() for x in page_num.split(" of ")]
        last_section = current_page == last_page
        title = f"{bem_val}: {title}".strip()
        return title, last_section
    else:
        return line_contents


def main() -> None:
    if len(sys.argv) < 5:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            sys.argv[1:],
        )
        return

    process_and_ingest_sys_args(sys, logger, _ingest_policy_pdfs)

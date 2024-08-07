import json
import logging
import sys

from smart_open import open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.html import get_text_from_html
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)

# Print INFO messages since this is often run from the terminal
# during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


NAME_KEY = "preferredPhrase"
CONTENT_KEY = "content"


def _ingest_cards(
    db_session: db.Session,
    guru_cards_filepath: str,
    doc_attribs: dict[str, str],
) -> None:
    with open(guru_cards_filepath, "r") as guru_cards_file:
        cards_as_json = json.load(guru_cards_file)

    for card in cards_as_json:
        logger.info(f"Processing card {card[NAME_KEY]!r}")

        # Strip the HTML of the content and return just the content
        name = card[NAME_KEY].strip()
        content = get_text_from_html(card[CONTENT_KEY])

        document = Document(name=name, content=content, **doc_attribs)
        db_session.add(document)

        embedding_model = app_config.sentence_transformer
        tokens = len(embedding_model.tokenizer.tokenize(content))
        mpnet_embedding = embedding_model.encode(content, show_progress_bar=False)
        chunk = Chunk(
            document=document, content=content, tokens=tokens, mpnet_embedding=mpnet_embedding
        )
        db_session.add(chunk)

        if tokens > embedding_model.max_seq_length:
            logger.warning(
                f"Card {name!r} has {tokens} tokens, which exceeds the embedding model's max sequence length."
            )


def main() -> None:
    if len(sys.argv) < 5:
        logger.warning(
            "Expecting 4 arguments: DATASET_ID BENEFIT_PROGRAM BENEFIT_REGION FILEPATH\n   but got: %s",
            sys.argv[1:],
        )
        return

    process_and_ingest_sys_args(sys, logger, _ingest_cards)

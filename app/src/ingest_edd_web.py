import json
import logging
import sys

from smart_open import open as smart_open

from src.adapters import db
from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.util.ingest_utils import process_and_ingest_sys_args

logger = logging.getLogger(__name__)


def _ingest_edd_web(
    db_session: db.Session,
    json_filepath: str,
    doc_attribs: dict[str, str],
) -> None:
    with smart_open(json_filepath, "r", encoding="utf-8") as json_file:
        json_items = json.load(json_file)

    for item in json_items:
        name = item["title"]
        logger.info("Processing %s (%s)", name, item["url"])

        content = item.get("main_content", item.get("main_primary"))
        assert content, f"Item {name} has no main_content or main_primary"

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
                "Chunk %s has %i tokens, which exceeds the embedding model's max sequence length.",
                name,
                tokens,
            )


def main() -> None:
    process_and_ingest_sys_args(sys.argv, logger, _ingest_edd_web)

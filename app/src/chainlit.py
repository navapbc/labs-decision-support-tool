import logging

from sentence_transformers import SentenceTransformer

import chainlit as cl
import src.adapters.db as db
from src.app_config import AppConfig
from src.format import format_guru_cards
from src.generate import generate
from src.retrieve import retrieve

logger = logging.getLogger(__name__)

embedding_model = SentenceTransformer(AppConfig().embedding_model)


@cl.on_message
async def main(message: cl.Message) -> None:
    logger.info(f"Received: {message.content!r}")

    with db.PostgresDBClient().get_session() as db_session:
        chunks = retrieve(
            db_session,
            embedding_model,
            message.content,
        )

    response = generate(message.content, context=chunks)
    formatted_guru_cards = format_guru_cards(chunks)

    await cl.Message(
        content=response + formatted_guru_cards,
    ).send()

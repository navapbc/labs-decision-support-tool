import logging

import chainlit as cl
import src.adapters.db as db
from src.auth import require_auth
from src.cache import get_embedding_model
from src.format import format_guru_cards
from src.generate import generate
from src.retrieve import retrieve

logger = logging.getLogger(__name__)

require_auth()


@cl.on_message
async def main(message: cl.Message) -> None:
    logger.info(f"Received: {message.content!r}")

    with db.PostgresDBClient().get_session() as db_session:
        chunks = retrieve(
            db_session,
            get_embedding_model(),
            message.content,
        )

    response = generate(message.content, context=chunks)
    formatted_guru_cards = format_guru_cards(chunks)

    await cl.Message(
        content=response + formatted_guru_cards,
    ).send()

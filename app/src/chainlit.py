import logging

import chainlit as cl
import src.adapters.db as db
from src.format import format_guru_cards
from src.generate import generate
from src.login import require_login
from src.retrieve import retrieve
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)

require_login()


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

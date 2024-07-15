import logging
from urllib.parse import parse_qs, urlparse

import chainlit as cl
import src.adapters.db as db
from src.format import format_guru_cards
from src.generate import generate
from src.login import require_login
from src.retrieve import retrieve
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)

require_login()


@cl.on_chat_start
async def start() -> None:
    chat_engine = engine_url_query_value()
    print("chat_engine", chat_engine)


def engine_url_query_value() -> str:
    url = cl.user_session.get("http_referer")
    logger.debug("URL: %s", url)

    # Using this suggestion: https://github.com/Chainlit/chainlit/issues/144#issuecomment-2227543547
    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    return qs.get("engine", ["default_engine"])[0]


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

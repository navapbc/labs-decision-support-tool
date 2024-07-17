import logging
import os
from urllib.parse import parse_qs, urlparse

import chainlit as cl
from src import chat_engine
from src.format import format_guru_cards
from src.login import require_login

logger = logging.getLogger(__name__)

require_login()


@cl.on_chat_start
async def start() -> None:
    engine_id = engine_url_query_value()
    logger.info("Engine ID: %s", engine_id)
    engine = chat_engine.create_engine(engine_id)
    if not engine:
        await cl.Message(
            author="backend",
            metadata={"engine": engine_id},
            content=f"Available engines: {chat_engine.available_engines()}",
        ).send()
        return

    cl.user_session.set("chat_engine", engine)
    await cl.Message(
        author="backend",
        metadata={"engine": engine_id},
        content=f"Chat engine started: {engine.name}",
    ).send()


def engine_url_query_value() -> str:
    url = cl.user_session.get("http_referer")
    logger.debug("Referer URL: %s", url)

    # Using this suggestion: https://github.com/Chainlit/chainlit/issues/144#issuecomment-2227543547
    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    return qs.get("engine", [os.environ.get("CHAT_ENGINE", "default_engine")])[0]


@cl.on_message
async def on_message(message: cl.Message) -> None:
    logger.info("Received: %r", message.content)

    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    try:
        result = engine.on_message(question=message.content)
        msg_content = result.response + format_guru_cards(result.chunks)
        await cl.Message(
            content=msg_content,
            metadata={chunk[0].document.name: chunk[1] for chunk in result.chunks},
        ).send()
    except Exception as err:  # pylint: disable=broad-exception-caught
        await cl.Message(
            author="backend",
            metadata={"error_class": err.__class__.__name__, "error": str(err)},
            content=f"{err.__class__.__name__}: {err}",
        ).send()
        # Re-raise error to have it in the logs
        raise err

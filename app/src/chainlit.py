import logging
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
    logger.info("engine: %s", engine_id)
    engine = chat_engine.create_engine(engine_id)
    if not engine:
        await cl.Message(
            author="backend",
            metadata={"engine": engine_id},
            content=f"Available engines: {chat_engine.available_engines()}",
        ).send()
        return

    cl.user_session.set("chat_engine", engine)
    engine.on_start()
    await cl.Message(
        author="backend",
        metadata={"engine": engine_id},
        content=f"Chat engine started: {engine.name}",
    ).send()


def engine_url_query_value() -> str:
    url = cl.user_session.get("http_referer")
    logger.debug("URL: %s", url)

    # Using this suggestion: https://github.com/Chainlit/chainlit/issues/144#issuecomment-2227543547
    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    return qs.get("engine", ["default_engine"])[0]


@cl.on_message
async def on_message(message: cl.Message) -> None:
    logger.info(f"Received: {message.content!r}")

    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    result = engine.on_message(question=message.content, cl_message=message)
    content = engine.format_answer_message(result)

    await cl.Message(content=content).send()

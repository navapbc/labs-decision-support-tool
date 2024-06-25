import logging

import chainlit as cl

from src.generate import generate

logger = logging.getLogger(__name__)


@cl.on_message
async def main(message: cl.Message) -> None:
    logger.info(f"Received: {message.content}")
    response = generate(message.content)
    await cl.Message(
        content=response,
    ).send()

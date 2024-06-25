import logging

import chainlit as cl

logger = logging.getLogger(__name__)


@cl.on_message
async def main(message: cl.Message) -> None:
    logger.info(f"Received: {message.content}")
    await cl.Message(
        content=f"Hello, world! Received: {message.content}",
    ).send()

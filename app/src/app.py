import logging

logger = logging.getLogger(__name__)

import chainlit as cl


@cl.on_message
async def main(message: cl.Message):
    logger.info(f"Received: {message.content}")
    await cl.Message(
        content=f"Hello, world! Received: {message.content}",
    ).send()

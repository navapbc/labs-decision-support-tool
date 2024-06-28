import logging

from sentence_transformers import SentenceTransformer

import chainlit as cl
import src.adapters.db as db
from src.app_config import AppConfig
from src.generate import generate
from src.retrieve import retrieve

logger = logging.getLogger(__name__)

embedding_model = SentenceTransformer(AppConfig().embedding_model)


@cl.on_message
async def main(message: cl.Message) -> None:
    logger.info(f"Received: {message.content}")

    with db.PostgresDBClient().get_session() as db_session:
        logger.info(f"Retrieving context for {message.content!r}")
        chunks_with_scores = retrieve(db_session, embedding_model, message.content)
        chunks = [chunk for chunk, _ in chunks_with_scores]
        for chunk in chunks:
            logger.info(f"Retrieved: {chunk.document.name!r}")

    response = generate(message.content, context=chunks)

    await cl.Message(
        content=response,
    ).send()

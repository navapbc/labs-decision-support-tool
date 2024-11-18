import logging
from typing import Optional

from asyncer import asyncify

from src.chat_engine import ChatEngineInterface, OnMessageResult
from src.generate import ChatHistory

logger = logging.getLogger(__name__)


async def run_engine_async(
    engine: ChatEngineInterface, question: str, chat_history: Optional[ChatHistory] = None
) -> OnMessageResult:
    logger.info("Received: %s", question)
    result = await asyncify(lambda: run_engine(engine, question, chat_history))()
    logger.info("Response: %s", result.response)
    return result


def run_engine(
    engine: ChatEngineInterface, question: str, chat_history: Optional[ChatHistory] = None
) -> OnMessageResult:
    result = engine.on_message(question, chat_history)
    return result

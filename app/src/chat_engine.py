import logging
from abc import ABC, abstractmethod
from typing import Mapping, Type

import src.adapters.db as db
from src.format import format_guru_cards
from src.generate import generate
from src.retrieve import retrieve
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)


class ChatEngineInterface(ABC):
    id: str
    name: str = "Chat Engine Interface"

    @abstractmethod
    def on_start(self):
        pass

    @abstractmethod
    def on_message(self, question: str, **kwargs):
        pass

    @abstractmethod
    def format_answer_message(self, result: dict):
        pass


def available_engines():
    return [engine_class.id for engine_class in ChatEngineInterface.__subclasses__()]


def create_engine(id: str) -> ChatEngineInterface | None:
    engines: Mapping[str, Type[ChatEngineInterface]] = {engine_class.id: engine_class for engine_class in ChatEngineInterface.__subclasses__()}  # type: ignore

    if id not in engines:
        return None

    chat_engine_class = engines[id]
    return chat_engine_class()


# Subclasses of ChatEngineInterface can be extracted into a separate file if it gets too large
class GuruMultiprogramEngine(ChatEngineInterface):
    id: str = "guru-multiprogram"
    name: str = "Guru Multi-program Chat Engine"

    def on_start(self):
        logger.info("chat_engine name: %s", self.name)

    def on_message(self, question: str, **_kwargs):
        logger.info("chat_engine name: %s", self.name)

        with db.PostgresDBClient().get_session() as db_session:
            chunks = retrieve(
                db_session,
                get_embedding_model(),
                question,
            )

        response = generate(question, context=chunks)
        return {"chunks": chunks, "response": response}

    def format_answer_message(self, result: dict):
        formatted_guru_cards = format_guru_cards(result["chunks"])
        return result["response"] + formatted_guru_cards

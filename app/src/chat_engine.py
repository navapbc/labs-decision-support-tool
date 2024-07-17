import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Row

import src.adapters.db as db
from src.db.models.document import Chunk
from src.generate import generate
from src.retrieve import retrieve_with_scores
from src.shared import get_embedding_model
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)


@dataclass
class OnMessageResult:
    response: str
    chunks: Sequence[Chunk] | Sequence[Row[tuple[Chunk, float]]]
    response_format: str


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    @abstractmethod
    def on_message(self, question: str) -> OnMessageResult:
        pass


def available_engines() -> list[str]:
    return [
        engine_class.engine_id
        for engine_class in all_subclasses(ChatEngineInterface)
        if hasattr(engine_class, "engine_id") and engine_class.engine_id
    ]


def create_engine(engine_id: str) -> ChatEngineInterface | None:
    if engine_id not in available_engines():
        return None

    chat_engine_class = next(
        engine_class
        for engine_class in all_subclasses(ChatEngineInterface)
        if hasattr(engine_class, "engine_id") and engine_class.engine_id == engine_id
    )
    return chat_engine_class()


# Subclasses of ChatEngineInterface can be extracted into a separate file if it gets too large
class GuruBaseEngine(ChatEngineInterface):
    def on_message(self, question: str) -> OnMessageResult:
        with db.PostgresDBClient().get_session() as db_session:
            chunks = retrieve_with_scores(
                db_session,
                get_embedding_model(),
                question,
            )

        response = generate(question, context=chunks)
        return OnMessageResult(response, chunks, response_format="with_score")


class GuruMultiprogramEngine(GuruBaseEngine):
    engine_id: str = "guru-multiprogram"
    name: str = "Guru Multi-program Chat Engine"


class GuruSnapEngine(GuruBaseEngine):
    engine_id: str = "guru-snap"
    name: str = "Guru SNAP Chat Engine"

    def on_message(self, question: str) -> OnMessageResult:
        # TODO: Only retrieve SNAP Guru cards https://navalabs.atlassian.net/browse/DST-328
        logger.warning("TODO: Only retrieve SNAP Guru cards")
        chunks: list[Chunk] = []
        response = "TEMP: Replace with generated response once chunks are correct"
        return OnMessageResult(response, chunks, response_format="no_score")


class PolicyMichiganEngine(ChatEngineInterface):
    engine_id: str = "policy-mi"
    name: str = "Michigan Bridges Policy Manual Chat Engine"

    def on_message(self, question: str) -> OnMessageResult:
        logger.warning("TODO: Retrieve from MI Policy Manual")
        chunks: list[Chunk] = []
        response = "TEMP: Replace with generated response once chunks are correct"
        return OnMessageResult(response, chunks, response_format="no_score")

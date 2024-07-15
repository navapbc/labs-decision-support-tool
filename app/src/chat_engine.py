import logging
from abc import ABC, abstractmethod
from typing import Type

import chainlit as cl
import src.adapters.db as db
from chainlit.input_widget import Slider, Switch
from src.db.models.document import Chunk
from src.format import format_guru_cards
from src.generate import generate
from src.retrieve import retrieve
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    @abstractmethod
    async def on_start(self) -> dict:
        pass

    @abstractmethod
    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        pass

    @abstractmethod
    def format_answer_message(self, results: dict) -> str:
        pass


def all_subclasses(cls: Type) -> set:
    return {cls}.union(s for c in cls.__subclasses__() for s in all_subclasses(c))


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
    use_snap_dataset_default = False
    use_multiprogram_dataset_default = False

    async def on_start(self) -> dict:
        chat_settings = cl.ChatSettings(
            [
                Slider(
                    id="temperature",
                    label="Temperature for primary LLM",
                    initial=0.1,
                    min=0,
                    max=2,
                    step=0.1,
                ),
                Slider(
                    id="retrieve_k",
                    label="Guru cards to retrieve",
                    initial=5,
                    min=1,
                    max=10,
                    step=1,
                ),
                Switch(
                    id="guru-snap", label="Guru cards: SNAP", initial=self.use_snap_dataset_default
                ),
                Switch(
                    id="guru-multiprogram",
                    label="Guru cards: Multi-program",
                    initial=self.use_multiprogram_dataset_default,
                ),
            ]
        )
        settings = await chat_settings.send()
        cl.user_session.set("settings", settings)
        return settings

    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        with db.PostgresDBClient().get_session() as db_session:
            chunks = retrieve(
                db_session,
                get_embedding_model(),
                question,
            )

        response = generate(question, context=chunks)
        return {"chunks": chunks, "response": response}

    def format_answer_message(self, results: dict) -> str:
        formatted_guru_cards = format_guru_cards(results["chunks"])
        return results["response"] + formatted_guru_cards


class GuruMultiprogramEngine(GuruBaseEngine):
    engine_id: str = "guru-multiprogram"
    name: str = "Guru Multi-program Chat Engine"
    use_multiprogram_dataset_default = True


class GuruSnapEngine(GuruBaseEngine):
    engine_id: str = "guru-snap"
    name: str = "Guru SNAP Chat Engine"
    use_snap_dataset_default = True

    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        # TODO: Only retrieve SNAP Guru cards https://navalabs.atlassian.net/browse/DST-328
        logger.warning("TODO: Only retrieve SNAP Guru cards")
        chunks: list[Chunk] = []
        response = "TEMP: Replace with generated response once chunks are correct"
        return {"chunks": chunks, "response": response}


class PolicyMichiganEngine(ChatEngineInterface):
    engine_id: str = "policy-mi"
    name: str = "Michigan Bridges Policy Manual Chat Engine"

    async def on_start(self) -> dict:
        return {}

    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        logger.warning("TODO: Retrieve from MI Policy Manual")
        chunks = ["TODO: Retrieve from MI Policy Manual"]
        response = "TEMP: Replace with generated response once chunks are correct"
        return {"chunks": chunks, "response": response}

    def format_answer_message(self, results: dict) -> str:
        # Placeholder for Policy Manual Citation format
        return f"TODO: Placeholder for Policy Manual Citation format. {results}"

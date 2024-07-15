import logging
from typing import Type
from abc import ABC, abstractmethod

import chainlit as cl
import src.adapters.db as db
from chainlit.input_widget import Slider, Switch
from src.format import format_guru_cards
from src.generate import generate
from src.retrieve import retrieve
from src.shared import get_embedding_model

logger = logging.getLogger(__name__)


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    @abstractmethod
    async def on_start(self) -> None:
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
    use_guru_snap_dataset = False
    use_guru_multiprogram_dataset = False

    async def on_start(self) -> None:
        logger.info("chat_engine name: %s", self.name)
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
                    id="guru-snap", label="Guru cards: SNAP", initial=self.use_guru_snap_dataset
                ),
                Switch(
                    id="guru-multiprogram",
                    label="Guru cards: Multi-program",
                    initial=self.use_guru_multiprogram_dataset,
                ),
            ]
        )
        settings = await chat_settings.send()
        cl.user_session.set("settings", settings)

    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        logger.info("chat_engine name: %s", self.name)

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
    use_guru_multiprogram_dataset = True


class GuruSnapEngine(GuruBaseEngine):
    engine_id: str = "guru-snap"
    name: str = "Guru SNAP Chat Engine"
    use_guru_snap_dataset = True

    def on_message(self, question: str, cl_message: cl.Message) -> dict:
        chunks = ["TODO: Only retrieve SNAP Guru cards"]
        response = "TEMP: Replace with generated response once chunks are correct"
        return {"chunks": chunks, "response": response}


class PolicyMichiganEngine(GuruBaseEngine):
    engine_id: str = "policy-mi"
    name: str = "Michigan Bridges Policy Manual Chat Engine"

    def format_answer_message(self, results: dict) -> str:
        # Placeholder for Policy Manual Citation format
        return f"TODO: Placeholder for Policy Manual Citation format. {results}"

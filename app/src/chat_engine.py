import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from src.db.models.document import ChunkWithScore
from src.generate import generate
from src.retrieve import retrieve_with_scores
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)


@dataclass
class OnMessageResult:
    response: str
    chunks_with_scores: Sequence[ChunkWithScore]


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    # Thresholds that determine which retrieved documents are shown in the UI
    docs_shown_max_num: int = 5
    docs_shown_min_score: float = 0.65

    # List of engine-specific configuration settings that can be set by the user.
    # The string elements must match the attribute names for the configuration setting.
    user_settings: list[str]

    def __init__(self) -> None:
        super().__init__()

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
    datasets: list[str] = []
    llm: str = "gpt-4o"

    # Thresholds that determine which documents are sent to the LLM
    retrieval_k: int = 8
    retrieval_k_min_score: float = 0.45

    user_settings = [
        "llm",
        "retrieval_k",
        "retrieval_k_min_score",
        "docs_shown_max_num",
        "docs_shown_min_score",
    ]

    def on_message(self, question: str) -> OnMessageResult:
        chunks_with_scores = retrieve_with_scores(
            question,
            retrieval_k=self.retrieval_k,
            retrieval_k_min_score=self.retrieval_k_min_score,
            datasets=self.datasets,
        )

        response = generate(self.llm, question, context=chunks_with_scores)
        return OnMessageResult(response, chunks_with_scores)


class GuruMultiprogramEngine(GuruBaseEngine):
    engine_id: str = "guru-multiprogram"
    name: str = "Guru Multi-program Chat Engine"
    datasets = ["guru-multiprogram"]


class GuruSnapEngine(GuruBaseEngine):
    engine_id: str = "guru-snap"
    name: str = "Guru SNAP Chat Engine"
    datasets = ["guru-snap"]


class PolicyMichiganEngine(ChatEngineInterface):
    engine_id: str = "policy-mi"
    name: str = "Michigan Bridges Policy Manual Chat Engine"

    def on_message(self, question: str) -> OnMessageResult:
        logger.warning("TODO: Retrieve from MI Policy Manual")
        chunks: Sequence[ChunkWithScore] = []
        response = "TEMP: Replace with generated response once chunks are correct"
        return OnMessageResult(response, chunks)

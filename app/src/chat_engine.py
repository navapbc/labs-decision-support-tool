import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Sequence

from src.citations import CitationFactory, create_prompt_context, split_into_subsections
from src.db.models.document import ChunkWithScore, Subsection
from src.format import format_bem_subsections, format_guru_cards, format_web_subsections
from src.generate import PROMPT, generate
from src.retrieve import retrieve_with_scores
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)


@dataclass
class OnMessageResult:
    response: str
    system_prompt: str
    chunks_with_scores: Sequence[ChunkWithScore]
    subsections: Sequence[Subsection]


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    # Function for formatting responses
    formatter: Callable

    # Thresholds that determine which retrieved documents are shown in the UI
    chunks_shown_max_num: int = 5
    chunks_shown_min_score: float = 0.65

    system_prompt: str = PROMPT

    # List of engine-specific configuration settings that can be set by the user.
    # The string elements must match the attribute names for the configuration setting.
    user_settings: list[str]

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def on_message(self, question: str, chat_history: list[dict[str, str]]) -> OnMessageResult:
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
class BaseEngine(ChatEngineInterface):
    datasets: list[str] = []
    llm: str = "gpt-4o"

    # Thresholds that determine which documents are sent to the LLM
    retrieval_k: int = 8
    retrieval_k_min_score: float = 0.45

    user_settings = [
        "llm",
        "retrieval_k",
        "retrieval_k_min_score",
        "chunks_shown_max_num",
        "chunks_shown_min_score",
        "system_prompt",
    ]

    def on_message(self, question: str, chat_history: list[dict[str, str]]) -> OnMessageResult:
        chunks_with_scores = retrieve_with_scores(
            question,
            retrieval_k=self.retrieval_k,
            retrieval_k_min_score=self.retrieval_k_min_score,
            datasets=self.datasets,
        )

        chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
        # Provide a factory to reset the citation id counter
        subsections = split_into_subsections(chunks, factory=CitationFactory())
        context_text = create_prompt_context(subsections)
        response = generate(self.llm, self.system_prompt, question, context_text, chat_history)
        return OnMessageResult(response, self.system_prompt, chunks_with_scores, subsections)


class GuruMultiprogramEngine(BaseEngine):
    engine_id: str = "guru-multiprogram"
    name: str = "Guru Multi-program Chat Engine"
    datasets = ["guru-multiprogram"]
    formatter = staticmethod(format_guru_cards)


class GuruSnapEngine(BaseEngine):
    engine_id: str = "guru-snap"
    name: str = "Guru SNAP Chat Engine"
    datasets = ["guru-snap"]
    formatter = staticmethod(format_guru_cards)


class BridgesEligibilityManualEngine(BaseEngine):
    retrieval_k: int = 10
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "bridges-eligibility-manual"
    name: str = "Michigan Bridges Eligibility Manual Chat Engine"
    datasets = ["bridges-eligibility-manual"]
    formatter = staticmethod(format_bem_subsections)


class CaEddWebEngine(BaseEngine):
    retrieval_k: int = 50
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "ca-edd-web"
    name: str = "CA EDD Web Chat Engine"
    datasets = ["ca-edd-web"]
    formatter = staticmethod(format_web_subsections)

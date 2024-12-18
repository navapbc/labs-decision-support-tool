import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional, Sequence

from src.citations import (
    CitationFactory,
    ResponseWithSubsections,
    create_prompt_context,
    split_into_subsections,
)
from src.db.models.document import ChunkWithScore, Subsection
from src.format import FormattingConfig, format_guru_cards
from src.generate import PROMPT, ChatHistory, MessageAttributes, analyze_message, generate
from src.retrieve import retrieve_with_scores
from src.util.class_utils import all_subclasses

logger = logging.getLogger(__name__)


class OnMessageResult(ResponseWithSubsections):
    def __init__(
        self,
        response: str,
        system_prompt: str,
        chunks_with_scores: Sequence[ChunkWithScore] | None = None,
        subsections: Sequence[Subsection] | None = None,
    ):
        super().__init__(response, subsections if subsections is not None else [])
        self.system_prompt = system_prompt
        self.chunks_with_scores = chunks_with_scores if chunks_with_scores is not None else []


class ChatEngineInterface(ABC):
    engine_id: str
    name: str

    # Configuration for formatting responses
    formatting_config: FormattingConfig

    # Function for formatting responses instead of the default
    # Only used by the old Guru chat engine
    formatter: Callable | None = None

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
    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
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

    formatting_config = FormattingConfig()

    def on_message(self, question: str, chat_history: Optional[ChatHistory]) -> OnMessageResult:
        attributes = analyze_message(self.llm, question)

        if attributes.needs_context:
            return self._build_response_with_context(question, attributes, chat_history)

        return self._build_response(question, attributes, chat_history)

    def _build_response(
        self,
        question: str,
        attributes: MessageAttributes,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        response = generate(
            self.llm,
            self.system_prompt,
            question,
            None,
            chat_history,
        )

        return OnMessageResult(response, self.system_prompt)

    def _build_response_with_context(
        self,
        question: str,
        attributes: MessageAttributes,
        chat_history: Optional[ChatHistory] = None,
    ) -> OnMessageResult:
        question_for_retrieval = (
            question if attributes.is_in_english else attributes.message_in_english
        )

        chunks_with_scores = retrieve_with_scores(
            question_for_retrieval,
            retrieval_k=self.retrieval_k,
            retrieval_k_min_score=self.retrieval_k_min_score,
            datasets=self.datasets,
        )

        chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
        # Provide a factory to reset the citation id counter
        subsections = split_into_subsections(chunks, factory=CitationFactory())
        context_text = create_prompt_context(subsections)

        response = generate(
            self.llm,
            self.system_prompt,
            question,
            context_text,
            chat_history,
        )

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


class CaEddWebEngine(BaseEngine):
    retrieval_k: int = 50
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "ca-edd-web"
    name: str = "CA EDD Web Chat Engine"
    datasets = ["CA EDD"]

    system_prompt = f"""You are an assistant to navigators who support clients (such as claimants, beneficiaries, families, and individuals) during the screening, application, and receipt of public benefits from California's Employment Development Department (EDD).
If you can't find information about the user's prompt in your context, don't answer it. If the user asks a question about a program not delivered by California's Employment Development Department (EDD), don't answer beyond pointing the user to the relevant trusted website for more information. Don't answer questions about tax credits (such as EITC, CTC) or benefit programs not delivered by EDD.
If a prompt is about an EDD program, but you can't tell which one, detect and clarify program ambiguity. Ask: "The EDD administers several programs such as State Disability Insurance (SDI), Paid Family Leave (PFL), and Unemployment Insurance (UI). I'm not sure which benefit program your prompt is about; could you let me know?"

{PROMPT}"""


class ImagineLaEngine(BaseEngine):
    retrieval_k: int = 50
    retrieval_k_min_score: float = -1

    # Note: currently not used
    chunks_shown_min_score: float = -1
    chunks_shown_max_num: int = 8

    engine_id: str = "imagine-la"
    name: str = "Imagine LA Chat Engine"
    datasets = ["CA EDD", "Imagine LA"]

    system_prompt = f"""You are an assistant to navigators who support clients-such as claimants, beneficiaries, families, and individuals-during the screening, application, and receipt of public benefits in California.
If you can't find information about the user's prompt in your context, don't answer it. If the user asks a question about a program not available in California, don't answer beyond pointing the user to the relevant trusted website for more information.
If a prompt is about a benefit program, but you can't tell which one, detect and clarify program ambiguity. Ask: "I'm not sure which benefit program your prompt is about; could you let me know? If you don't know what benefit program might be helpful, you can also describe what you need and I can make a recommendation."

{PROMPT}"""

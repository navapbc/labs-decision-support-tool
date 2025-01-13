import asyncio
import logging
import pprint
from typing import Any
from urllib.parse import parse_qs, urlparse

from asyncer import asyncify

import chainlit as cl
from chainlit.input_widget import InputWidget, Select, Slider, TextInput
from chainlit.types import AskFileResponse
from src import chat_engine
from src.app_config import app_config
from src.batch_process import batch_process
from src.chat_engine import ChatEngineInterface, OnMessageResult
from src.format import build_accordions
from src.generate import ChatHistory, get_models
from src.login import require_login

logger = logging.getLogger(__name__)

require_login()


@cl.on_chat_start
async def start() -> None:
    url = cl.user_session.get("http_referer")
    logger.debug("Referer URL: %s", url)
    query_values = url_query_values(url)

    engine_id = query_values.pop("engine", app_config.chat_engine)
    logger.info("Engine ID: %s", engine_id)

    engine = _init_chat_engine(engine_id)
    if not engine:
        await cl.Message(
            author="backend",
            metadata={"engine": engine_id},
            content=f"Available engines: {chat_engine.available_engines()}",
        ).send()
        return

    input_widgets = _init_chat_settings(engine, query_values)
    settings = await cl.ChatSettings(input_widgets).send()
    logger.info("Initialized settings: %s", pprint.pformat(settings, indent=4))
    if query_values:
        logger.warning("Unused URL query parameters: %r", query_values)
        await cl.Message(
            author="backend",
            metadata={"url": url},
            content=f"Unused URL query parameters: {query_values}",
        ).send()

    user = cl.user_session.get("user")
    await cl.Message(
        author="backend",
        metadata={"engine": engine_id, "settings": settings},
        content=f"{engine.name} started {f'for {user}' if user else ''}",
    ).send()


def url_query_values(url: str) -> dict[str, str]:
    # Using this suggestion: https://github.com/Chainlit/chainlit/issues/144#issuecomment-2227543547
    parsed_url = urlparse(url)
    # For a given query key, only the first value is used
    query_values = {key: values[0] for key, values in parse_qs(parsed_url.query).items()}
    logger.info("URL query values: %r", query_values)
    return query_values


def _init_chat_engine(engine_id: str) -> ChatEngineInterface | None:
    engine = chat_engine.create_engine(engine_id)
    if engine:
        cl.user_session.set("chat_engine", engine)
        return engine
    return None


def _init_chat_settings(
    engine: ChatEngineInterface, query_values: dict[str, str]
) -> list[InputWidget]:
    input_widgets: list[InputWidget] = [
        _WIDGET_FACTORIES[setting_name](
            query_values.pop(setting_name, None)
            or getattr(app_config, setting_name, None)
            or getattr(engine, setting_name)
        )
        for setting_name in engine.user_settings
        if setting_name in _WIDGET_FACTORIES
    ]
    return input_widgets


@cl.on_settings_update
async def update_settings(settings: dict[str, Any]) -> Any:
    logger.info("Updating settings: %s", pprint.pformat(settings, indent=4))
    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    for setting_id, value in settings.items():
        setattr(engine, setting_id, value)
    await cl.Message(
        author="backend",
        metadata=settings,
        content="Settings updated for this session.",
    ).send()


# The ordering of _WIDGET_FACTORIES affects the order of the settings in the UI
_WIDGET_FACTORIES = {
    "llm": lambda default_value: Select(
        id="llm",
        label="Language model",
        initial_value=default_value,
        items=get_models(),
    ),
    "retrieval_k": lambda default_value: Slider(
        id="retrieval_k",
        label="Number of citations to retrieve for generating LLM response",
        initial=default_value,
        min=0,
        max=50,
        step=1,
    ),
    "retrieval_k_min_score": lambda initial_value: Slider(
        id="retrieval_k_min_score",
        label="Minimum citation score required for generating LLM response",
        initial=initial_value,
        min=-1,
        max=1,
        step=0.25,
    ),
    "chunks_shown_max_num": lambda initial_value: Slider(
        id="chunks_shown_max_num",
        label="Maximum number of retrieved citations to show in the UI",
        initial=initial_value,
        min=0,
        max=10,
        step=1,
    ),
    "chunks_shown_min_score": lambda initial_value: Slider(
        id="chunks_shown_min_score",
        label="Minimum citation score required to show citation in the UI",
        initial=initial_value,
        min=-1,
        max=1,
        step=0.25,
    ),
    "system_prompt": lambda initial_value: TextInput(
        id="system_prompt",
        label="System prompt",
        initial=initial_value,
        multiline=True,
    ),
}


def extract_raw_chat_history(messages: list[cl.Message]) -> ChatHistory:
    raw_chat_history: ChatHistory = []
    for message in messages:
        if message.type == "assistant_message":
            # Response to the user's query
            raw_chat_history.append(
                {
                    "role": "assistant",
                    "content": (
                        message.metadata["raw_response"]
                        if message.metadata and "raw_response" in message.metadata
                        else message.content
                    ),
                }
            )
        elif message.type == "user_message":
            # User's query
            raw_chat_history.append({"role": "user", "content": message.content})
        else:
            logger.warning("Unexpected message type: %s: %r", message.type, message.content)
    return raw_chat_history


@cl.on_message
async def on_message(message: cl.Message) -> None:
    logger.info("Received: %r", message.content)
    chat_context = cl.chat_context.get()
    # chat_context has the user query as the last item; exclude it from the chat history
    chat_history = extract_raw_chat_history(chat_context[:-1])

    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")

    if message.content.lower() == "batch processing":
        # The AskFileMessage cannot be called inside code run by asyncio.create_task,
        # or the Chainlit UI will freeze indefinitely
        files = await cl.AskFileMessage(
            content="Please upload a CSV file with a `question` column.",
            accept=["text/csv"],
            max_size_mb=20,
            timeout=180,
        ).send()

        if files:
            asyncio.create_task(_batch_proccessing(files[0]))
        return

    try:
        result = await asyncify(lambda: engine.on_message(message.content, chat_history))()
        logger.info("Raw response: %s", result.response)
        msg_content = build_accordions(
            subsections=result.subsections,
            raw_response=result.response,
            config=engine.formatting_config,
        )

        await cl.Message(
            content=msg_content,
            metadata=_get_retrieval_metadata(result),
        ).send()
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.exception("Error processing message: %r", message.content)
        await cl.Message(
            author="backend",
            metadata={"error_class": err.__class__.__name__, "error": str(err)},
            content=f"{err.__class__.__name__}: {err}",
        ).send()
        # Re-raise error to have it in the logs
        raise err


def _get_retrieval_metadata(result: OnMessageResult) -> dict:
    return {
        "system_prompt": result.system_prompt,
        "chunks": [
            {
                "document.name": chunk_with_score.chunk.document.name,
                "chunk.id": str(chunk_with_score.chunk.id),
                "score": chunk_with_score.score,
            }
            for chunk_with_score in result.chunks_with_scores
        ],
        "subsections": [
            {
                "id": citations.id,
                "chunk.id": str(citations.chunk.id),
                "document.name": citations.chunk.document.name,
                "headings": citations.text_headings,
                "text": citations.text,
            }
            for citations in result.subsections
        ],
        "raw_response": result.response,
    }


async def _batch_proccessing(file: AskFileResponse) -> None:
    try:
        engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
        # Make the synchronous batch_process function non-blocking
        result_file_path = await cl.make_async(batch_process)(file.path, engine)

        # E.g., "abcd.csv" to "abcd_results.csv"
        result_file_name = file.name.removesuffix(".csv") + "_results.csv"
        await cl.Message(
            author="backend",
            content="File processed, results attached.",
            elements=[cl.File(name=result_file_name, path=result_file_path)],
        ).send()

    except ValueError as err:
        logger.error("Error processing file %r: %s", file.name, err)
        await cl.Message(
            author="backend",
            content=f"Error processing file: {err}",
        ).send()

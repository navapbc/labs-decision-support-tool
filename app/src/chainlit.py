import logging
import pprint
from typing import Any
from urllib.parse import parse_qs, urlparse

import chainlit as cl
from chainlit.input_widget import InputWidget, Slider
from src import chat_engine
from src.app_config import app_config
from src.chat_engine import ChatEngineInterface
from src.format import format_guru_cards
from src.login import require_login

logger = logging.getLogger(__name__)

require_login()


@cl.on_chat_start
async def start() -> None:
    query_values = url_query_values()
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

    settings = await _init_chat_settings(engine, query_values)
    await cl.Message(
        author="backend",
        metadata={"engine": engine_id, "settings": str(settings)},
        content=f"{engine.name} started with settings:\n{pprint.pformat(settings, indent=3)}",
    ).send()


def url_query_values() -> dict[str, str]:
    url = cl.user_session.get("http_referer")
    logger.debug("Referer URL: %s", url)

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


async def _init_chat_settings(engine: ChatEngineInterface) -> dict[str, Any]:
    input_widgets: list[InputWidget] = [
        _WIDGET_FACTORIES[setting_name](getattr(engine, setting_name))
        for setting_name in engine.user_settings
        if setting_name in _WIDGET_FACTORIES
    ]
    settings = await cl.ChatSettings(input_widgets).send()
    logger.info("Initialized settings: %s", pprint.pformat(settings, indent=4))
    return settings


@cl.on_settings_update
def update_settings(settings: dict[str, Any]) -> Any:
    logger.info("Updating settings: %s", pprint.pformat(settings, indent=4))
    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    for setting_id, value in settings.items():
        setattr(engine, setting_id, value)


# The ordering of _WIDGET_FACTORIES affects the order of the settings in the UI
_WIDGET_FACTORIES = {
    "retrieval_k": lambda default_value: Slider(
        id="retrieval_k",
        label="Number of documents to retrieve for generating LLM response",
        initial=default_value,
        min=0,
        max=10,
        step=1,
    ),
    "retrieval_k_min_score": lambda default_value: Slider(
        id="retrieval_k_min_score",
        label="Minimum document score required for generating LLM response",
        initial=default_value,
        min=-1,
        max=1,
        step=0.25,
    ),
    "docs_shown_max_num": lambda default_value: Slider(
        id="docs_shown_max_num",
        label="Maximum number of retrieved documents to show in the UI",
        initial=default_value,
        min=0,
        max=10,
        step=1,
    ),
    "docs_shown_min_score": lambda default_value: Slider(
        id="docs_shown_min_score",
        label="Minimum document score required to show document in the UI",
        initial=default_value,
        min=-1,
        max=1,
        step=0.25,
    ),
}


def _init_chat_engine(engine_id: str) -> ChatEngineInterface | None:
    engine = chat_engine.create_engine(engine_id)
    if engine:
        cl.user_session.set("chat_engine", engine)
        return engine
    return None


async def _init_chat_settings(
    engine: ChatEngineInterface, query_values: dict[str, str]
) -> dict[str, Any]:
    input_widgets: list[InputWidget] = [
        _WIDGET_FACTORIES[setting_name](
            query_values.pop(setting_name, None) or getattr(engine, setting_name)
        )
        for setting_name in engine.user_settings
        if setting_name in _WIDGET_FACTORIES
    ]
    if query_values:
        logger.warning("Unused query values: %r", query_values)
    settings = await cl.ChatSettings(input_widgets).send()
    logger.info("Initialized settings: %s", pprint.pformat(settings, indent=4))
    return settings


@cl.on_settings_update
def update_settings(settings: dict[str, Any]) -> Any:
    logger.info("Updating settings: %s", pprint.pformat(settings, indent=4))
    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    for setting_id, value in settings.items():
        setattr(engine, setting_id, value)


# The ordering of _WIDGET_FACTORIES affects the order of the settings in the UI
_WIDGET_FACTORIES = {
    "retrieval_k": lambda initial_value: Slider(
        id="retrieval_k",
        label="Number of documents to retrieve for generating LLM response",
        initial=initial_value,
        min=0,
        max=10,
        step=1,
    ),
    "retrieval_k_min_score": lambda initial_value: Slider(
        id="retrieval_k_min_score",
        label="Minimum document score required for generating LLM response",
        initial=initial_value,
        min=-1,
        max=1,
        step=0.25,
    ),
    "docs_shown_max_num": lambda initial_value: Slider(
        id="docs_shown_max_num",
        label="Maximum number of retrieved documents to show in the UI",
        initial=initial_value,
        min=0,
        max=10,
        step=1,
    ),
    "docs_shown_min_score": lambda initial_value: Slider(
        id="docs_shown_min_score",
        label="Minimum document score required to show document in the UI",
        initial=initial_value,
        min=-1,
        max=1,
        step=0.25,
    ),
}


@cl.on_message
async def on_message(message: cl.Message) -> None:
    logger.info("Received: %r", message.content)

    engine: chat_engine.ChatEngineInterface = cl.user_session.get("chat_engine")
    try:
        result = engine.on_message(question=message.content)
        msg_content = result.response + format_guru_cards(
            docs_shown_max_num=engine.docs_shown_max_num,
            docs_shown_min_score=engine.docs_shown_min_score,
            chunks_with_scores=result.chunks_with_scores,
        )
        chunk_titles_and_scores: dict[str, float] = {}
        for chunk_with_score in result.chunks_with_scores:
            title = chunk_with_score.chunk.document.name
            chunk_titles_and_scores |= {title: chunk_with_score.score}

        await cl.Message(
            content=msg_content,
            metadata=chunk_titles_and_scores,
        ).send()
    except Exception as err:  # pylint: disable=broad-exception-caught
        await cl.Message(
            author="backend",
            metadata={"error_class": err.__class__.__name__, "error": str(err)},
            content=f"{err.__class__.__name__}: {err}",
        ).send()
        # Re-raise error to have it in the logs
        raise err

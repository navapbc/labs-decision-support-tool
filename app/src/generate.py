import json
import logging
import os
from typing import Any

from litellm import completion
from pydantic import BaseModel

from src.app_config import app_config

logger = logging.getLogger(__name__)


def get_models() -> dict[str, str]:
    """
    Returns a dictionary of the available models, based on
    which environment variables are set. The keys are the
    human-formatted model names, and the values are the model
    IDs for use with LiteLLM.
    """
    models: dict[str, str] = {}
    if "OPENAI_API_KEY" in os.environ:
        models |= {"OpenAI GPT-4o": "gpt-4o"}
    if "ANTHROPIC_API_KEY" in os.environ:
        models |= {"Anthropic Claude 3.5 Sonnet": "claude-3-5-sonnet-20240620"}
    if "OLLAMA_HOST" in os.environ:
        import ollama

        ollama_models = {
            f"Ollama {model['name']}": f"ollama/{model['name']}"
            for model in ollama.list()["models"]
        }
        models |= ollama_models
    return models


ChatHistory = list[dict[str, str]]


def generate(
    llm: str,
    system_prompt: str,
    query: str,
    context_text: str | None = None,
    chat_history: ChatHistory | None = None,
) -> str:
    """
    Returns a string response from an LLM model, based on a query input.
    """
    messages = [
        {
            "content": system_prompt,
            # System message for high-level framing that governs the assistant response
            "role": "system",
        }
    ]
    logger.info("Using system prompt: %s", system_prompt)

    if context_text:
        messages.append(
            {
                "content": f"Use the following context to answer the question: {context_text}",
                "role": "system",
            },
        )

    if chat_history:
        messages.extend(chat_history)

    messages.append({"content": query, "role": "user"})
    logger.debug("Calling %s for query: %s with context:\n%s", llm, query, context_text)
    response = completion(
        model=llm, messages=messages, **completion_args(llm), temperature=app_config.temperature
    )

    return response["choices"][0]["message"]["content"]


def completion_args(llm: str) -> dict[str, Any]:
    if llm.startswith("ollama/"):
        return {"api_base": os.environ["OLLAMA_HOST"]}
    return {}


class MessageAttributes(BaseModel):
    original_language: str
    is_in_english: bool
    message_in_english: str
    needs_context: bool


def analyze_message(llm: str, system_prompt: str, message: str) -> MessageAttributes:
    response = (
        completion(
            model=llm,
            messages=[
                {
                    "content": system_prompt,
                    "role": "system",
                },
                {
                    "content": message,
                    "role": "user",
                },
            ],
            response_format=MessageAttributes,
            temperature=app_config.temperature,
            **completion_args(llm),
        )
        .choices[0]
        .message.content
    )

    logger.info("Analyzed message: %s", response)

    response_as_json = json.loads(response)
    return MessageAttributes.model_validate(response_as_json)

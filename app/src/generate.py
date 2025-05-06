import json
import logging
import os
from typing import Any, AsyncGenerator, TypeVar

import boto3
import botocore.exceptions
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
    if _has_aws_access():
        # If you get "You don't have access to the model with the specified model ID." error,
        # remember to request access to Bedrock models ...aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess
        models |= {
            # Append 'us.' to the model - https://github.com/BerriAI/litellm/issues/8851
            "Bedrock Claude 3.7 Sonnet": "bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            # Only add models that support 'response_format' and 'json_schema' - https://docs.litellm.ai/docs/completion/json_mode#check-model-support
            # Otherwise update the code to use some other method to get structured output
        }
    if "OLLAMA_HOST" in os.environ:
        import ollama

        ollama_models = {
            f"Ollama {model['name']}": f"ollama/{model['name']}"
            for model in ollama.list()["models"]
        }
        models |= ollama_models
    return models


def _has_aws_access() -> bool:
    env = os.environ.get("ENVIRONMENT", "local")
    if env != "local":
        return True

    # LiteLLM requires these env variables to access Bedrock models - https://docs.litellm.ai/docs/providers/bedrock
    if "AWS_ACCESS_KEY_ID" not in os.environ or "AWS_SECRET_ACCESS_KEY" not in os.environ:
        return False
    if "AWS_REGION" not in os.environ and "AWS_DEFAULT_REGION" in os.environ:
        os.environ["AWS_REGION"] = os.environ["AWS_DEFAULT_REGION"]
    try:
        # Check credentials are valid
        boto3.client("sts").get_caller_identity()
        return True
    except botocore.exceptions.ClientError:
        return False


ChatHistory = list[dict[str, str]]


def _prepare_messages(
    system_prompt: str,
    query: str,
    context_text: str | None = None,
    chat_history: ChatHistory | None = None,
) -> list[dict[str, str]]:
    """
    Prepares the messages list for LLM completion, used by both streaming and non-streaming functions.
    """
    messages = [
        {
            "content": system_prompt,
            "role": "system",
        }
    ]
    logger.debug("Using system prompt: %s", system_prompt)

    if context_text:
        messages.append(
            {
                "content": f"Use the following context to answer the question: {context_text}",
                "role": "system",
            },
        )

    if chat_history:
        messages.extend(chat_history)

    messages.append({"content": query + " Write at a sixth grade reading level.", "role": "user"})
    return messages


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
    messages = _prepare_messages(system_prompt, query, context_text, chat_history)
    logger.debug("Calling %s for query: %s with context:\n%s", llm, query, context_text)

    response = completion(
        model=llm, messages=messages, **completion_args(llm), temperature=app_config.temperature
    )

    return response["choices"][0]["message"]["content"]


async def generate_streaming_async(
    llm: str,
    system_prompt: str,
    query: str,
    context_text: str | None = None,
    chat_history: ChatHistory | None = None,
) -> AsyncGenerator[str, None]:
    """
    Returns an async generator that yields chunks of the response from an LLM model.
    """
    messages = _prepare_messages(system_prompt, query, context_text, chat_history)
    logger.debug(
        "Async streaming from %s for query: %s with context:\n%s", llm, query, context_text
    )

    response_stream = completion(
        model=llm,
        messages=messages,
        stream=True,  # Enable streaming
        **completion_args(llm),
        temperature=app_config.temperature,
    )

    for chunk in response_stream:
        if content := chunk.choices[0].delta.content:
            yield content


def completion_args(llm: str) -> dict[str, Any]:
    if llm.startswith("ollama/"):
        return {"api_base": os.environ["OLLAMA_HOST"]}
    return {}


class MessageAttributes(BaseModel):
    "'Message' refers to the user's message/question"
    needs_context: bool
    # The language of the user's question
    users_language: str
    # The user's message/question translated by the LLM so that RAG retrieval is in English
    translated_message: str


MessageAttributesT = TypeVar("MessageAttributesT", bound=MessageAttributes)


def analyze_message(
    llm: str, system_prompt: str, message: str, response_format: type[MessageAttributesT]
) -> MessageAttributesT:
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
            response_format=response_format,
            temperature=app_config.temperature,
            **completion_args(llm),
        )
        .choices[0]
        .message.content
    )

    logger.info("Analyzed message: %s", response)

    response_as_json = json.loads(response)
    return response_format.model_validate(response_as_json)

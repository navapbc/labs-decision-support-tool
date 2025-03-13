import json
import logging
import os
import time
from typing import Any, TypeVar, Optional

from litellm import completion
from pydantic import BaseModel

from src.app_config import app_config
from src.profiling import profile_function, add_metadata

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


def track_llm_api_call(func):
    """Decorator to track LLM API call timing and metadata."""
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        
        # Track model loading/setup time
        model_start = time.perf_counter()
        model = kwargs.get("model", "unknown")
        model_end = time.perf_counter()
        add_metadata("model_load_time", model_end - model_start)
        add_metadata("model_name", model)
        
        # Track API request
        try:
            api_start = time.perf_counter()
            result = func(*args, **kwargs)
            api_end = time.perf_counter()
            
            # Track timing
            api_duration = api_end - api_start
            total_duration = api_end - start_time
            add_metadata("api_request_time", api_duration)
            add_metadata("total_llm_time", total_duration)
            add_metadata("api_overhead", total_duration - api_duration)
            
            # Track rate limits and quotas if available
            headers = getattr(result, "headers", {})
            if headers:
                if "x-ratelimit-remaining" in headers:
                    add_metadata("rate_limit_remaining", headers["x-ratelimit-remaining"])
                if "x-ratelimit-reset" in headers:
                    add_metadata("rate_limit_reset", headers["x-ratelimit-reset"])
                    
            return result
        except Exception as e:
            # Track API errors
            add_metadata("api_error", str(e))
            add_metadata("api_error_type", e.__class__.__name__)
            raise
            
    return wrapper


@profile_function("llm_inference")
@track_llm_api_call
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
    
    # Track token counts
    total_input_tokens = sum(len(m["content"].split()) for m in messages)
    add_metadata("input_tokens", total_input_tokens)
    
    # Add more detailed profiling
    add_metadata("system_prompt_length", len(system_prompt))
    add_metadata("query_length", len(query))
    add_metadata("context_length", len(context_text) if context_text else 0)
    add_metadata("chat_history_length", len(chat_history) if chat_history else 0)
    add_metadata("num_messages", len(messages))
    
    # Track system prompt vs context size
    system_prompt_tokens = len(system_prompt.split())
    context_tokens = len(context_text.split()) if context_text else 0
    add_metadata("system_prompt_tokens", system_prompt_tokens)
    add_metadata("context_tokens", context_tokens)
    add_metadata("system_prompt_percentage", system_prompt_tokens / total_input_tokens * 100 if total_input_tokens > 0 else 0)
    add_metadata("context_percentage", context_tokens / total_input_tokens * 100 if total_input_tokens > 0 else 0)
    
    # Time the actual API call separately
    api_call_start = time.perf_counter()
    response = completion(
        model=llm, messages=messages, **completion_args(llm), temperature=app_config.temperature
    )
    api_call_duration = time.perf_counter() - api_call_start
    add_metadata("api_call_duration", api_call_duration)
    
    # Track output tokens
    output_text = response["choices"][0]["message"]["content"]
    output_tokens = len(output_text.split())
    add_metadata("output_tokens", output_tokens)
    
    return output_text


def completion_args(llm: str) -> dict[str, Any]:
    if llm.startswith("ollama/"):
        return {"api_base": os.environ["OLLAMA_HOST"]}
    return {}


class MessageAttributes(BaseModel):
    "'Message' refers to the user's message/question"
    needs_context: bool
    # The user's message/question translated by the LLM so that RAG retrieval is in English
    translated_message: str


MessageAttributesT = TypeVar("MessageAttributesT", bound=MessageAttributes)


@profile_function("analyze_message")
@track_llm_api_call
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

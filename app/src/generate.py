import logging
import os
from typing import Any, Sequence

from litellm import completion

from src.db.models.document import ChunkWithScore

logger = logging.getLogger(__name__)

PROMPT = """Provide answers in plain language written at the average American reading level.
Use bullet points. Keep your answers brief, max of 5 sentences.
Keep your answers as similar to your knowledge text as you can"""


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


def generate(
    llm: str,
    query: str,
    context: Sequence[ChunkWithScore] | None = None,
) -> str:
    """
    Returns a string response from an LLM model, based on a query input.
    """

    if context:
        context_text = "\n\n".join(
            [
                chunk_with_score.chunk.document.name + "\n" + chunk_with_score.chunk.content
                for chunk_with_score in context
            ]
        )
        messages = [
            {
                "content": PROMPT,
                "role": "system",
            },
            {
                "content": f"Use the following context to answer the question: {context_text}",
                "role": "system",
            },
            {"content": query, "role": "user"},
        ]

    else:
        messages = [
            {
                "content": PROMPT,
                "role": "system",
            },
            {"content": query, "role": "user"},
        ]

    logger.info("Calling %s for query: %s", llm, query)
    response = completion(model=llm, messages=messages, **completion_args(llm))
    return response["choices"][0]["message"]["content"]


def completion_args(llm: str) -> dict[str, Any]:
    if llm.startswith("ollama/"):
        return {"api_base": os.environ["OLLAMA_HOST"]}
    return {}

import logging
import os
from typing import Any

from litellm import completion

from src.app_config import app_config

logger = logging.getLogger(__name__)

PROMPT = """Provide answers in plain language written at the average American reading level.
Use bullet points. Keep your answers brief, max of 5 sentences.
Keep your answers as similar to your knowledge text as you can.

When referencing the context, do not quote directly.
Use the provided citation numbers (e.g., (citation-1)) to indicate when you are drawing from the context.
To cite multiple sources at once, you can append citations like so: (citation-1)(citation-2), etc.
Place the citations after any closing punctuation for the sentence.
For example: 'This is a sentence that draws on information from the context.(citation-1)'

Example Answer:
If the client and their roommate purchase and prepare food separately, they can be considered different SNAP (FAP) groups. For instance:
- They can be classified as different SNAP (FAP) groups if they purchase and prepare food separately.(citation-1)(citation-3)
"""


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
    system_prompt: str,
    query: str,
    context_text: str | None = None,
) -> str:
    """
    Returns a string response from an LLM model, based on a query input.
    """
    messages = [
        {
            "content": system_prompt,
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

    messages.append({"content": query, "role": "user"})

    logger.info("Calling %s for query: %s with context:\n%s", llm, query, context_text)
    response = completion(
        model=llm, messages=messages, **completion_args(llm), temperature=app_config.temperature
    )

    return response["choices"][0]["message"]["content"]


def completion_args(llm: str) -> dict[str, Any]:
    if llm.startswith("ollama/"):
        return {"api_base": os.environ["OLLAMA_HOST"]}
    return {}

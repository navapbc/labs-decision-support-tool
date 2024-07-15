import os
from typing import Sequence

from litellm import completion

from src.db.models.document import Chunk

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

    if "OPENAI_API_KEY" in os.environ:
        return {"OpenAI GPT-4o": "gpt-4o"}
    if "OLLAMA_HOST" in os.environ:
        ollama_models = {}
        import ollama

        models = ollama.list()
        for model in models["models"]:
            ollama_models[f"Ollama {model['name']}"] = f"ollama/{model['name']}"
        return ollama_models
    return {}


def generate(query: str, context: Sequence[Chunk] | None = None) -> str:
    """
    Returns a string response from an LLM model, based on a query input.
    """
    if context:
        context_text = "\n\n".join(
            [chunk.document.name + "\n" + chunk.content for chunk in context]
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
    response = completion(model="gpt-4o", messages=messages)
    return response["choices"][0]["message"]["content"]

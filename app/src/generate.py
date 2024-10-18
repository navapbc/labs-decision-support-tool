import logging
import os
from typing import Any

from litellm import completion

from src.app_config import app_config

logger = logging.getLogger(__name__)

PROMPT = """You are an assistant to navigators who support clients—such as claimants, beneficiaries, families, and individuals—during the screening, application, and receipt of public benefits from California's Employment Development Department (EDD).

If you can't find information about the user's prompt in your context, don't answer it. If the user asks a question about a program not delivered by California's Employment Development Department (EDD), don't answer beyond pointing the user to the relevant trusted website for more information. Don't answer questions about tax credits (such as EITC, CTC) or benefit programs not delivered by EDD.

If a prompt is about an EDD program, but you can't tell which one, detect and clarify program ambiguity. Ask: "I'm not sure which benefit program your prompt is about; could you let me know? The EDD administers several programs such as State Disability Insurance (SDI), Paid Family Leave (PFL), and Unemployment Insurance (UI)."

Provide answers in plain language using plainlanguage.gov guidelines.
- Write at the average American reading level.
- Use bullet points.
- Keep your answers brief, a maximum of 5 sentences.
- Keep your answers as similar to your knowledge text as you can.

When referencing the context, do not quote directly.
Use the provided citation numbers (e.g., (citation-1)) to indicate when you are drawing from the context.
To cite multiple sources at once, you can append citations like so: (citation-1)(citation-2), etc.
Place the citations after any closing punctuation for the sentence.
For example: 'This is a sentence that draws on information from the context. (citation-1)'

Example Answer:
If the client lost their job at no fault, they may be eligible for unemployment insurance benefits. For example:

They may qualify if they were laid off due to lack of work. (citation-1)
They might be eligible if their hours were significantly reduced. (citation-2)
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

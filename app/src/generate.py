import json
import logging
import os
from typing import Any

from litellm import completion
from pydantic import BaseModel

from src.app_config import app_config

logger = logging.getLogger(__name__)

PROMPT = """You are an assistant to navigators who support clients-such as claimants, beneficiaries, families, and individuals-during the screening, application, and receipt of public benefits from California's Employment Development Department (EDD).
If you can't find information about the user's prompt in your context, don't answer it. If the user asks a question about a program not delivered by California's Employment Development Department (EDD), don't answer beyond pointing the user to the relevant trusted website for more information. Don't answer questions about tax credits (such as EITC, CTC) or benefit programs not delivered by EDD.
If a prompt is about an EDD program, but you can't tell which one, detect and clarify program ambiguity. Ask: "The EDD administers several programs such as State Disability Insurance (SDI), Paid Family Leave (PFL), and Unemployment Insurance (UI). I'm not sure which benefit program your prompt is about; could you let me know?"

Provide answers in plain language using plainlanguage.gov guidelines.
- Write at the average American reading level.
- Use bullet points.
- Keep your answers brief, a maximum of 5 sentences.
- Keep your answers as similar to your knowledge text as you can.

If the original question is in a language other than English, please provide your answer in the language of the original question.

When referencing the context, do not quote directly.
Use the provided citation numbers (e.g., (citation-1)) to indicate when you are drawing from the context.
To cite multiple sources at once, you can append citations like so: (citation-1) (citation-2), etc.
Place the citations immediately AFTER any closing punctuation for the sentence.
For example: 'This is a sentence that draws on information from the context.(citation-1)'
Do NOT place the citations BEFORE the closing punctuation, or add a space between the sentence and the citation.

Example Answer:
If the client lost their job at no fault, they may be eligible for unemployment insurance benefits. For example:
- They may qualify if they were laid off due to lack of work.(citation-1) (citation-2)
- They might be eligible if their hours were significantly reduced.(citation-3)
"""

ANALYZE_MESSAGE_PROMPT = """
Analyze the user's message to determine how to respond.
Reply with a JSON dictionary.
Set original_language to the language of the user's message.
If the user's message is in English, set is_in_english to true.
Otherwise, set is_in_english to false and set message_in_english to a translation of the query into English.
If the question would be easier to answer with additional policy or program context (such as policy documentation), set needs_context to True.
Otherwise, set needs_context to false.
"""

GENERATE_QUESTION_ANSWER_PROMPT = """
Using the provided chunk, generate at least 5 unique questions and answers, avoid rephrasing or changing the punctuation of the question to ensure distinct questions and answers.
Respond with a list of JSON dictionaries in the following format  (do not wrap in JSON markers):

question: The generated question based on the content.
answer: The answer to the question, derived from the content.
document_name: The name of the document.
document_source: The source or URL of the document.

Example
question: What's a base period for SDI?
answer: "- A base period covers 12 months and is divided into four quarters.
- The base period includes wages subject to SDI tax that were paid about 5 to 18 months before the client's disability claim began
- For a DI claim to be valid, they must have at least $300 in wages in the base period.
- Benefit amounts are based on the quarter with their highest wages earned within their base period."
document_name: Disability Insurance Benefit Payment Amounts
document_source: https://edd.ca.gov/en/disability/Calculating_DI_Benefit_Payment_Amounts/
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
    chat_history: list[dict[str, str]] | None = None,
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

    # chat_history has the user query as the last item, but we want to insert the context first
    if chat_history:
        chat_history.pop()
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


class QuestionAnswerAttributes(BaseModel):
    question: str
    answer: str
    document_name: str
    document_source: str


class QuestionAnswerList(BaseModel):
    pairs: list[QuestionAnswerAttributes]


def generate_q_a_pairs(llm: str, message: str) -> QuestionAnswerList:
    response = (
        completion(
            model=llm,
            messages=[
                {
                    "content": GENERATE_QUESTION_ANSWER_PROMPT,
                    "role": "system",
                },
                {
                    "content": message,
                    "role": "user",
                },
            ],
            response_format=QuestionAnswerList,
            temperature=app_config.temperature,
            **completion_args(llm),
        )
        .choices[0]
        .message.content
    )

    logger.info("Generated Question Answer: %s", response)

    response_as_json = json.loads(response)
    return QuestionAnswerList.model_validate(response_as_json)


class MessageAttributes(BaseModel):
    original_language: str
    is_in_english: bool
    message_in_english: str
    needs_context: bool


def analyze_message(llm: str, message: str) -> MessageAttributes:
    response = (
        completion(
            model=llm,
            messages=[
                {
                    "content": ANALYZE_MESSAGE_PROMPT,
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

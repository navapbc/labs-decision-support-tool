import csv
import json
from litellm import completion
import logging

import os
from pydantic import BaseModel


from src.app_config import app_config
from src.db.models.document import Document
from src.generate import completion_args


logger = logging.getLogger(__name__)

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


def generate_question_answer_pair(
    document: Document, num_of_chunks: int
) -> list[QuestionAnswerAttributes]:
    generated_question_anwers = generate_q_a_pairs(
        llm="gpt-4o",
        message=f"Please use the following content to create {num_of_chunks} question(s) answer pairs. Content: {document.content}",
    )
    return generated_question_anwers.pairs


def write_question_answer_json_to_csv(
    file_path: str, fields: list[str], q_a_json: list[QuestionAnswerAttributes]
) -> None:
    needs_header = (
        True
        if os.path.exists(file_path)
        and os.stat(file_path).st_size == 0
        or not os.path.exists(file_path)
        else False
    )

    with open(file_path, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        if needs_header:
            writer.writeheader()
        for question in q_a_json:
            writer.writerow(dict(question))

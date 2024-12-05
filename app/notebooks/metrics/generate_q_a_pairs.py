import csv
import json
from typing import Optional
from litellm import completion
from hashlib import md5

import os
from pydantic import BaseModel
from uuid import UUID

from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.generate import completion_args


GENERATE_QUESTION_ANSWER_PROMPT = """
Using the provided text, generate unique questions and answers, avoid rephrasing or changing the punctuation of the question to ensure distinct questions and answers.
Respond with a list of JSON dictionaries in the following format (do not wrap in JSON markers):
question: The generated question based on the content.
answer: The answer to the question, derived from the content.

Example
question: What's a base period for SDI?
answer: "- A base period covers 12 months and is divided into four quarters.
- The base period includes wages subject to SDI tax that were paid about 5 to 18 months before the client's disability claim began
- For a DI claim to be valid, they must have at least $300 in wages in the base period.
- Benefit amounts are based on the quarter with their highest wages earned within their base period."
"""


class QuestionAnswerPair(BaseModel):
    question: str
    answer: str


class QuestionAnswerAttributes(QuestionAnswerPair):
    document_name: str
    document_source: str
    document_id: UUID
    chunk_id: Optional[UUID]
    content_hash: str
    dataset: str


class QuestionAnswerList(BaseModel):
    pairs: list[QuestionAnswerPair]


def generate_question_answer_pairs(llm: str, message: str) -> QuestionAnswerList:
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
    response_as_json = json.loads(response)
    return QuestionAnswerList.model_validate(response_as_json)


def process_document_or_chunk(
    document_or_chunk: Document | Chunk,
    num_of_chunks: int,
    llm: str,
    dataset: str,
) -> list[QuestionAnswerAttributes]:
    generated_question_answers = generate_question_answer_pairs(
        llm=llm,
        message=f"Please use the following content to create {num_of_chunks} question-answer pairs. Content: {document_or_chunk.content}",
    )
    question_answer_list: list[QuestionAnswerAttributes] = []

    for generated_question_answer in generated_question_answers.pairs:
        is_document = isinstance(document_or_chunk, Document)
        # use chunk document if is_document is false
        document = document_or_chunk if is_document else document_or_chunk.document
        question_answer_item = QuestionAnswerAttributes(
            document_id=document.id,
            document_name=document.name,
            document_source=document.source,
            question=generated_question_answer.question,
            answer=generated_question_answer.answer,
            chunk_id=None if is_document else document_or_chunk.id,
            content_hash=md5(document_or_chunk.content.encode('utf-8'), usedforsecurity=False).hexdigest(),
            dataset=dataset,
        )
        question_answer_list.append(question_answer_item)

    return question_answer_list


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

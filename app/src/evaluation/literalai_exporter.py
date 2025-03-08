import argparse
import csv
import functools
import logging
import json
import pickle
import sys

from typing import NamedTuple, Optional
from datetime import datetime
from literalai import LiteralClient, Thread, Step
from literalai.filter import Filter, OrderBy

from src.app_config import app_config

logger = logging.getLogger(__name__)
# Configure logging since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@functools.cache
def literalai() -> LiteralClient:
    if app_config.literal_api_key_for_api:
        return LiteralClient(api_key=app_config.literal_api_key_for_api)
    return LiteralClient()


# @functools.cache
# @property
def get_project_id() -> str:
    client = literalai()
    proj_id = client.api.get_my_project_id()
    logger.info("Project ID: %r", proj_id)
    return proj_id


def query_threads_since(start_date: datetime, end_date: datetime) -> list[Thread]:
    start_date = start_date.isoformat()
    filters: list[Filter] = [
        Filter(field="createdAt", operator="gte", value=start_date),
        Filter(field="createdAt", operator="lt", value=end_date),
    ]
    logger.info("Query filter: %r", filters)
    order_by: OrderBy = OrderBy(column="createdAt", direction="ASC")

    client = literalai()
    threads = []
    after = None
    while True:
        response = client.api.get_threads(filters=filters, order_by=order_by, after=after)
        after = response.pageInfo.endCursor
        threads += response.data
        logger.info("Got %r of %r total threads", len(threads), response.totalCount)
        if not response.pageInfo.hasNextPage:
            assert (
                len(threads) == response.totalCount
            ), f"Expected {response.totalCount} threads, but got only {len(threads)}"
            return threads

    raise RuntimeError("Didn't get last page of responses")


class QARow(NamedTuple):
    # uniquely identifies the thread in Literal AI; can have several associated questions
    thread_id: str
    # uniquely identifies the question in Literal AI
    question_id: str
    # question's timestamp
    timestamp: str
    # ids submitted in request
    user_id: str
    agency_id: str
    session_id: str
    # user's question
    question: str
    # LLM's generated answer
    answer: str
    # benefit_program
    program: Optional[str]
    # links to citations in the order they are referenced in the answer
    citation_links: Optional[str]
    # dataset and document name/title for each citation
    citation_sources: Optional[str]
    # another clue to signal that the QA pair follows another QA pair in the same thread
    has_chat_history: bool

    @property
    def lai_link(self):
        return (
            f"https://cloud.getliteral.ai/projects/{project_id}/logs/"
            "threads/{self.thread_id}?currentStepId={self.question_id}"
        )

    @classmethod
    def from_lai_thread(cls, thread: Thread, question_step: Step, answer_step: Step):
        assert question_step, "Question step must not be None"
        # question_step.id is used to create the link to Literal AI
        assert question_step.id, "Question step id must not be None"
        # start_time can also be used to distinguish question-answer pairs
        assert question_step.start_time, "Question step start_time must not be None"

        assert question_step.type == "user_message", "Question step must be a user_message"
        assert answer_step.type == "assistant_message", "Answer step must be an assistant_message"

        # output["content"] is the text shown in the chatbot UI
        assert question_step.output
        assert question_step.output["content"]
        assert answer_step.output
        assert answer_step.output["content"]

        # Handle custom metadata
        assert question_step.metadata
        assert answer_step.metadata
        attribs = answer_step.metadata.get("attributes", None)
        citations = answer_step.metadata.get("citations", None)

        return QARow(
            thread_id=thread.id,
            question_id=question_step.id,
            timestamp=question_step.start_time,
            user_id=question_step.metadata["request"]["user_id"],
            agency_id=question_step.metadata["request"]["agency_id"],
            session_id=question_step.metadata["request"]["session_id"],
            question=question_step.output["content"],
            answer=answer_step.output["content"],
            program=attribs["benefit_program"] if attribs else None,
            citation_links=("\n".join(c["uri"] for c in citations) if citations else None),
            citation_sources=(
                "\n".join(f"{c['source_dataset']}: {['source_name']}" for c in citations)
                if citations
                else None
            ),
            has_chat_history=bool(answer_step.metadata.get("chat_history", None)),
        )


def to_csv(threads: list[Thread]):
    qa_pairs = []
    for th in threads:
        assert th.steps
        steps = {step.id: step for step in th.steps}
        pairs = [
            # assert th.steps[step.parentId], f"Parent step {step.parentId} not found"
            QARow.from_lai_thread(
                thread=th, question_step=steps.pop(step.parent_id), answer_step=steps.pop(step.id)
            )
            for step in th.steps
            if step.parent_id
        ]
        for remaining in steps:
            logger.info("Step %r has no parent", remaining)
            # print(json.dumps(pair, indent=2))
        qa_pairs += pairs

    # import pdb; pdb.set_trace()
    fields = QARow._fields  # ["thread_id", "question", "answer", "lai_link"]
    with open("lai_pairs.csv", "w", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for pair in qa_pairs:
            writer.writerow({k: getattr(pair, k, "") for k in fields})


def _save_threads(threads: list[Thread]):
    with open("response.json", "w", encoding="utf-8") as f:
        thread_dicts = [thread.to_dict() for thread in threads]
        f.write(json.dumps(thread_dicts, indent=2))
    with open("response.pickle", "wb") as file:
        pickle.dump(threads, file)


def _load_response() -> list[Thread]:
    print("Loading from pickle")
    with open("response.pickle", "rb") as file:
        return pickle.load(file)


QUERY = False
if QUERY:
    project_id = get_project_id()
else:
    project_id = "Decision-Support-Tool---Imagine-LA-FEcqNEkhUJ71"
    # project_id="PROD-Decision-Support-Tool---Imagine-LA-Zu5f2WjplboI"


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("start", help="(inclusive) beginning datetime of threads to export")
    parser.add_argument("end", help="(exclusive) end datetime of threads to export")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    if QUERY:
        start_date = datetime.fromisoformat(args.start)  # ("2025-03-05T00:00:00.000Z")
        end_date = datetime.fromisoformat(args.end)
        threads = query_threads_since(start_date, end_date)
        _save_threads(threads)

    to_csv(_load_response())


if __name__ == "__main__":
    main()

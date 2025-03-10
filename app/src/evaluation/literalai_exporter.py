import argparse
import csv
import functools
import logging
import sys
from datetime import datetime
from typing import IO, NamedTuple, Optional

from literalai import LiteralClient, Step, Thread
from literalai.filter import Filter, OrderBy

from src.app_config import app_config

logger = logging.getLogger(__name__)
# Configure logging since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@functools.cache
def literalai() -> LiteralClient:  # pragma: no cover
    if app_config.literal_api_key_for_api:
        return LiteralClient(api_key=app_config.literal_api_key_for_api)
    return LiteralClient()


def get_project_id() -> str:
    client = literalai()
    return client.api.get_my_project_id()


def query_threads(start_date: datetime, end_date: datetime) -> list[Thread]:
    filters: list[Filter] = [
        Filter(field="createdAt", operator="gte", value=start_date.isoformat()),
        Filter(field="createdAt", operator="lt", value=end_date.isoformat()),
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


class QARow(NamedTuple):
    project_id: str
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
    def lai_link(self) -> str:
        return (
            f"https://cloud.getliteral.ai/projects/{self.project_id}/logs/"
            f"threads/{self.thread_id}?currentStepId={self.question_id}"
        )

    @classmethod
    def from_lai_thread(
        cls, project_id: str, thread: Thread, question_step: Step, answer_step: Step
    ) -> "QARow":
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
            project_id=project_id,
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
                "\n".join(f"{c['source_dataset']}: {c['source_name']}" for c in citations)
                if citations
                else None
            ),
            has_chat_history=bool(answer_step.metadata.get("chat_history", None)),
        )


def convert_to_qa_rows(project_id: str, threads: list[Thread]) -> list[QARow]:
    qa_pairs = []
    for th in threads:
        assert th.steps
        logger.info("Thread %r has %r steps", th.id, len(th.steps))
        steps = {step.id: step for step in th.steps}
        pairs = [
            QARow.from_lai_thread(
                project_id=project_id,
                thread=th,
                # Pop out referenced steps to later check for remaining steps
                question_step=steps.pop(step.parent_id),
                answer_step=steps.pop(step.id),
            )
            for step in th.steps
            if step.parent_id
        ]
        qa_pairs += pairs

        for remaining in steps.keys():
            logger.info("Ignoring dangling step %r", remaining)
    return qa_pairs


def save_csv(qa_pairs: list[QARow], csv_file: IO) -> None:
    fields = [field for field in QARow._fields if field != "project_id"]
    writer = csv.DictWriter(csv_file, fieldnames=fields)
    writer.writeheader()
    for pair in qa_pairs:
        writer.writerow({k: getattr(pair, k, "") for k in fields})


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("start", help="(inclusive) beginning datetime of threads to export")
    parser.add_argument("end", help="(exclusive) end datetime of threads to export")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    start_date = datetime.fromisoformat(args.start)
    end_date = datetime.fromisoformat(args.end)

    project_id = get_project_id()
    logger.info("Project ID: %r", project_id)
    threads = query_threads(start_date, end_date)
    qa_rows = convert_to_qa_rows(project_id, threads)
    with open(f"{project_id}-lai_pairs.csv", "w", encoding="utf-8") as f:
        save_csv(qa_rows, f)

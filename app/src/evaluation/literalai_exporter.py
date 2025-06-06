import argparse
import csv
import logging
import sys
from datetime import datetime
from typing import IO, Any, NamedTuple, Optional

from literalai import Step, Thread

from src.util import literalai_util as lai

logger = logging.getLogger(__name__)
# Configure logging since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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
    citation_links: list[str]
    # dataset and document name/title for each citation
    citation_sources: list[str]
    # another clue to signal that the QA pair follows another QA pair in the same thread
    has_chat_history: bool
    # Feedback score values
    scores: list[float]
    # Feedback comments
    comments: list[str]

    @property
    def lai_link(self) -> str:
        return (
            f"https://cloud.getliteral.ai/projects/{self.project_id}/logs/"
            f"threads/{self.thread_id}?currentStepId={self.question_id}"
        )

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "User ID": self.user_id,
            "Date": datetime.fromisoformat(self.timestamp).strftime("%m/%d/%Y"),
            "Question": self.question,
            "Response": self.answer,
            "LiteralAI Thread": self.lai_link,
            "Agency ID": self.agency_id,
            "Session ID": self.session_id,
            "Program": self.program if self.program else "",
            "Citation Links": "\n".join(self.citation_links) if self.citation_links else "",
            "Citation Sources": "\n".join(self.citation_sources) if self.citation_sources else "",
            "Has Chat History": str(self.has_chat_history),
            "Thread ID": self.thread_id,
            "Timestamp": self.timestamp,
            "Feedback Scores": self._simplify_list(self.scores),
            "Feedback Comments": self._simplify_list(self.comments),
        }

    def _simplify_list(self, items: list[Any]) -> Any:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return items

    @classmethod
    def from_lai_thread(
        cls, project_id: str, thread: Thread, question_step: Step, answer_step: Step
    ) -> "QARow":
        assert question_step, "Question step must not be None"
        # question_step.id is used to create the link to Literal AI
        assert question_step.id, "Question step id must not be None"
        # start_time can also be used to distinguish question-answer pairs
        assert question_step.start_time, "Question step start_time must not be None"

        assert (
            question_step.type == "user_message"
        ), f"Question step must be a user_message, not {question_step.type!r}"
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
            citation_links=[c["uri"] for c in citations] if citations else [],
            citation_sources=(
                [f"{c.get('source_dataset', '')}: {c.get('source_name', '')}" for c in citations]
                if citations
                else []
            ),
            has_chat_history=bool(answer_step.metadata.get("chat_history", None)),
            scores=[s.value for s in answer_step.scores] if answer_step.scores else [],
            comments=[s.comment or "" for s in answer_step.scores] if answer_step.scores else [],
        )


def convert_to_qa_rows(project_id: str, threads: list[Thread]) -> list[QARow]:
    qa_pairs = []
    for th in threads:
        if not th.steps:
            logger.warning("Thread %r has no steps", th.id)
            continue
        if th.tags and "chainlit" in th.tags:
            logger.info("Skipping thread %r with chainlit tag", th.id)
            continue
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
    fields = list(qa_pairs[0].to_csv_dict().keys()) if qa_pairs else []
    writer = csv.DictWriter(csv_file, fieldnames=fields)
    writer.writeheader()
    for pair in qa_pairs:
        writer.writerow(pair.to_csv_dict())


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("start", help="(inclusive) beginning datetime of threads to export")
    parser.add_argument("end", help="(exclusive) end datetime of threads to export")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    start_date = datetime.fromisoformat(args.start)
    end_date = datetime.fromisoformat(args.end)

    project_id = lai.get_project_id()
    logger.info("Project ID: %r", project_id)
    threads = lai.query_threads_between(start_date, end_date)
    qa_rows = convert_to_qa_rows(project_id, threads)
    with open(f"{project_id}-lai_pairs.csv", "w", encoding="utf-8") as f:
        save_csv(qa_rows, f)

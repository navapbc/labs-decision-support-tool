import csv
import functools
import json
import os
import pickle
from typing import NamedTuple, Optional
from datetime import datetime
from literalai import LiteralClient, Thread, Step
from literalai.filter import Filter, OrderBy

from src.app_config import app_config


@functools.cache
def literalai() -> LiteralClient:
    """
    This needs to be a function so that it's not immediately instantiated upon
    import of this module and so that it can mocked in tests.
    """
    if app_config.literal_api_key_for_api:
        return LiteralClient(api_key=app_config.literal_api_key_for_api)
    return LiteralClient()


def query_threads_since(client: LiteralClient, date: datetime):
    since_date = date.isoformat()  # strftime("%Y-%m-%d")
    # list[Filter[Literal['id', 'createdAt', 'name', 'stepType', 'stepName',
    #   'stepOutput', 'metadata', 'tokenCount', 'tags', 'participantId',
    #   'participantIdentifiers', 'scoreValue', 'duration']]]
    filters: list[Filter] = [Filter(field="createdAt", operator="gte", value=since_date)]

    # OrderBy[Literal['createdAt', 'tokenCount']]
    order_by: OrderBy = OrderBy(column="createdAt", direction="ASC")

    threads = []
    has_next_page = True
    after = None
    while has_next_page:
        response = client.api.get_threads(filters=filters, order_by=order_by, after=after)
        # print(response.to_dict())
        # Save response to file
        has_next_page = response.pageInfo.hasNextPage
        after = response.pageInfo.endCursor

        print(f"totalCount: {response.totalCount}, has_next_page: {has_next_page}, after: {after}")
        threads += response.data

    with open("response.json", "w", encoding="utf-8") as f:
        thread_dicts = [thread.to_dict() for thread in threads]
        f.write(json.dumps(thread_dicts, indent=2))
    # Serialize the object to a file
    with open("response.pickle", "wb") as file:
        pickle.dump(threads, file)


class LaiCitation(NamedTuple):
    citation_id: str
    uri: str
    source_dataset: str
    source_name: str

    @classmethod
    def from_json(cls, obj: dict):
        return LaiCitation(
            citation_id=obj["citation_id"],
            uri=obj["uri"],
            source_dataset=obj["source_dataset"],
            source_name=obj["source_name"],
        )


class LaiStep(NamedTuple):
    id: str
    # threadId: str
    parentId: str
    startTime: str
    endTime: str

    type: str
    # name: str
    output: str

    benefit_program: Optional[str]
    needs_context: Optional[bool]
    # raw_response: str

    has_chat_history: bool
    citations: Optional[dict[str, LaiCitation]]

    @classmethod
    def from_json(cls, obj: dict):
        attribs = obj["metadata"].get("attributes", None)
        citations = obj["metadata"].get("citations", None)
        chat_history = obj["metadata"].get("chat_history", None)
        return LaiStep(
            id=obj["id"],
            parentId=obj["parentId"],
            startTime=obj["startTime"],
            endTime=obj["endTime"],
            type=obj["type"],
            # name=obj["name"],
            output=obj["output"]["content"],
            benefit_program=attribs["benefit_program"] if attribs else None,
            needs_context=attribs["needs_context"] if attribs else None,
            # raw_response=obj["metadata"].get("raw_response"),
            has_chat_history=bool(chat_history),
            citations=(
                {c["citation_id"]: LaiCitation.from_json(c) for c in citations}
                if citations
                else None
            ),
        )


class LaiThread(NamedTuple):
    id: str
    createdAt: str
    participant: str
    steps: dict[str, LaiStep]

    @classmethod
    def from_json(cls, obj: dict):
        steps = {step_obj["id"]: LaiStep.from_json(step_obj) for step_obj in obj["steps"]}
        return LaiThread(
            id=obj["id"],
            createdAt=obj["createdAt"],
            participant=obj["participant"]["identifier"],
            steps=steps,
        )


class QARow(NamedTuple):
    thread_id: str
    question_id: str
    question_timestamp: str
    user_id: str
    agency_id: str
    session_id: str
    question: str
    answer: str
    program: Optional[str]
    citation_links: Optional[str]
    citations: Optional[dict[str, str]]
    has_chat_history: bool

    @property
    def lai_link(self):
        return f"https://cloud.getliteral.ai/projects/{project_id}/logs/threads/{self.thread_id}?currentStepId={self.question_id}"

    # @classmethod
    # def from_lai_steps(cls, thread: LaiThread, question_step: LaiStep, answer_step: LaiStep):
    #     assert question_step.type == "user_message", "Question step must be a user_message"
    #     assert answer_step.type == "assistant_message", "Answer step must be an assistant_message"
    #     return QARow(
    #         thread_id=thread.id,
    #         question_id=question_step.id,
    #         question=question_step.output,
    #         answer=answer_step.output,
    #         program=answer_step.benefit_program,
    #         has_chat_history=answer_step.has_chat_history,
    #     )

    @classmethod
    def from_lai_steps2(cls, thread: Thread, question_step: Step, answer_step: Step):
        assert question_step, "Question step must not be None"
        assert question_step.id, "Question step id must not be None"
        assert question_step.start_time, "Question step start_time must not be None"

        assert question_step.type == "user_message", "Question step must be a user_message"
        assert answer_step.type == "assistant_message", "Answer step must be an assistant_message"

        assert question_step.output
        assert question_step.output["content"]
        assert answer_step.output
        assert answer_step.output["content"]

        assert question_step.metadata
        assert answer_step.metadata
        attribs = answer_step.metadata.get("attributes", None)
        chat_history = answer_step.metadata.get("chat_history", None)
        citations = answer_step.metadata.get("citations", None)

        return QARow(
            thread_id=thread.id,
            question_id=question_step.id,
            question_timestamp=question_step.start_time,
            user_id=question_step.metadata["request"]["user_id"],
            agency_id=question_step.metadata["request"]["agency_id"],
            session_id=question_step.metadata["request"]["session_id"],
            question=question_step.output["content"],
            answer=answer_step.output["content"],
            # TODO: add to API
            program=attribs["benefit_program"] if attribs else None,
            citation_links=("\n".join(c["uri"] for c in citations) if citations else None),
            citations=({c["citation_id"]: c["uri"] for c in citations} if citations else None),
            has_chat_history=bool(chat_history),
        )


def to_csv(threads: list[Thread]):
    qa_pairs = []
    for th in threads:
        assert th.steps
        steps = {step.id: step for step in th.steps}
        pairs = [
            # assert th.steps[step.parentId], f"Parent step {step.parentId} not found"
            QARow.from_lai_steps2(thread=th, question_step=steps[step.parent_id], answer_step=step)
            for step in th.steps
            if step.parent_id
        ]
        for pair in pairs:
            qa_pairs.append(pair)
            print(json.dumps(pair, indent=2))

    # import pdb; pdb.set_trace()
    fields = QARow._fields  # ["thread_id", "question", "answer", "lai_link"]
    with open("lai_pairs.csv", "w", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for pair in qa_pairs:
            writer.writerow({k: getattr(pair, k, "") for k in fields})


# def json_to_csv(json_obj: dict):
#     # import pdb; pdb.set_trace()
#     threads = [LaiThread.from_json(thread_obj) for thread_obj in json_obj["data"]]
#     qa_pairs = []
#     for th in threads:
#         # print(json.dumps(th, indent=2))
#         # print(list(json_obj.keys()))

#         pairs = [
#             QARow.from_lai_steps(
#                 thread=th, question_step=th.steps[step.parentId], answer_step=step
#             )
#             for step in th.steps.values()
#             if step.parentId
#         ]
#         for pair in pairs:
#             qa_pairs.append(pair)
#             print(json.dumps(pair, indent=2))

#     fields = ["thread_id", "question", "answer"]
#     with open("lai_pairs.csv", "w", encoding="utf-8") as f:
#         writer = csv.DictWriter(f, fieldnames=fields)
#         writer.writeheader()
#         for pair in qa_pairs:
#             writer.writerow({k: getattr(pair, k, "") for k in fields})


def query():
    client = literalai()
    date = datetime.fromisoformat("2025-03-05T00:00:00.000Z")
    query_threads_since(client, date)


def load_response() -> list[Thread]:
    # with open("response.json", "r") as f:
    #     return json.load(f)
    with open("response.pickle", "rb") as file:
        return pickle.load(file)


if False:
    query()
    client = literalai()
    project_id = client.api.get_my_project_id()
    print(project_id)
else:
    project_id = "Decision-Support-Tool---Imagine-LA-FEcqNEkhUJ71"
    # project_id="PROD-Decision-Support-Tool---Imagine-LA-Zu5f2WjplboI"
to_csv(load_response())

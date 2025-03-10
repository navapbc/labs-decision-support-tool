import logging
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock

import pytest
from literalai import Step, Thread
from literalai.my_types import PageInfo

from src.evaluation import literalai_exporter
from src.evaluation.literalai_exporter import (
    convert_to_qa_rows,
    get_project_id,
    query_threads,
    save_csv,
)

THREADS = [Thread(f"th_{i}") for i in range(18)]


class MockLiteralAIApi:
    def __init__(self):
        self.get_threads_counter = 0
        self.responses = [THREADS[:5], THREADS[5:10], THREADS[10:]]

    def get_my_project_id(self):
        return "Test_Project_1234ABC"

    def get_threads(self, filters=None, **kwargs):
        threads = self.responses[self.get_threads_counter]
        self.get_threads_counter += 1

        response = MagicMock()
        response.data = threads
        response.totalCount = len(THREADS)
        response.pageInfo = PageInfo(
            hasNextPage=threads != self.responses[-1],
            startCursor=threads[0].id,
            endCursor=threads[-1].id,
        )
        return response


@pytest.fixture
def literalai_client(monkeypatch):
    mock_lai_client = MagicMock()
    mock_lai_client.api = MockLiteralAIApi()
    monkeypatch.setattr(literalai_exporter, "literalai", lambda: mock_lai_client)


def test_get_project_id(literalai_client):
    assert get_project_id() == "Test_Project_1234ABC"


def test_query_threads(literalai_client):
    start_date = datetime.fromisoformat("2025-03-06")
    end_date = datetime.fromisoformat("2025-03-07")
    threads = query_threads(start_date, end_date)
    assert len(threads) == len(THREADS)


def create_threads(num: int) -> list[Thread]:
    threads = []
    for i in range(num):
        th = Thread(f"th_{i}")
        q_step = Step(type="user_message")
        q_step.output = {"content": "Q1"}
        q_step.metadata = {
            "request": {"user_id": "U1", "agency_id": "Agency1", "session_id": "sesh1"}
        }
        a_step = Step(type="assistant_message", parent_id=q_step.id)
        a_step.output = {"content": "A1"}
        a_step.metadata = {
            "attributes": {
                "benefit_program": "prog1",
                "chat_history": [],
                "citations": [
                    {"uri": "uri1", "source_dataset": "dataset1", "source_name": "title1"}
                ],
            }
        }
        th.steps = [
            q_step,
            a_step,
        ]
        threads.append(th)
    return threads


def append_dangling_step(thread: Thread):
    step = Step(type="user_message")
    step.output = {"content": "Q1"}
    step.metadata = {"request": {"user_id": "U1", "agency_id": "Agency1", "session_id": "sesh1"}}
    assert thread.steps
    thread.steps.append(step)
    return step


def test_convert_to_qa_rows_and_save_csv(caplog):
    threads = create_threads(3)
    dangling_step = append_dangling_step(threads[1])
    project_id = "Test_Project_1234ABC"
    with caplog.at_level(logging.INFO):
        qa_rows = convert_to_qa_rows(project_id, threads)
    assert len(qa_rows) == 3
    assert f"Ignoring dangling step {dangling_step.id!r}"

    mock_csv_file = StringIO()
    save_csv(qa_rows, mock_csv_file)
    mock_csv_file.seek(0)
    csv_lines = mock_csv_file.readlines()
    print("".join(csv_lines))
    assert len(csv_lines) == 4

    # Roughly check the contents of the CSV file
    assert (
        "thread_id,question_id,timestamp,user_id,agency_id,session_id,question,answer,program,citation_links,citation_sources,has_chat_history"
        in csv_lines[0]
    )
    for line in csv_lines[1:]:
        assert line.startswith("Test_Project_1234ABC,th_")
        assert ",U1,Agency1,sesh1,Q1,A1,prog1," in line

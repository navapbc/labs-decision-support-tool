import logging
from io import StringIO

from literalai import Step, Thread

from src.evaluation.literalai_exporter import convert_to_qa_rows, save_csv


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
    "A dangling step is not referenced in a question-answer pair"
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
    assert len(csv_lines) == 4

    # Roughly check the contents of the CSV file
    assert (
        "thread_id,question_id,timestamp,user_id,agency_id,session_id,question,answer,program,citation_links,citation_sources,has_chat_history"
        in csv_lines[0]
    )
    for line in csv_lines[1:]:
        assert line.startswith("th_")
        # Check for metadata
        assert ",U1,Agency1,sesh1,Q1,A1,prog1," in line

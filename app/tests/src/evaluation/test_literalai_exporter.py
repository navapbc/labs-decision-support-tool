import csv
import logging
from io import StringIO

from literalai import Score, Step, Thread

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
    with caplog.at_level(logging.INFO):
        qa_rows = convert_to_qa_rows("Test_Project_1234ABC", threads)
    assert len(qa_rows) == 3
    assert f"Ignoring dangling step {dangling_step.id!r}"

    mock_csv_file = StringIO()
    save_csv(qa_rows, mock_csv_file)

    csv_lines = mock_csv_file.getvalue().splitlines()
    assert (
        csv_lines[0]
        == "User ID,Date,Question,Response,LiteralAI Thread,Agency ID,Session ID,Program,Citation Links,Citation Sources,Has Chat History,Thread ID,Timestamp,Feedback Scores,Feedback Comments"
    )

    for line in csv_lines[1:]:
        assert line.startswith(
            "U1",
        )
        # Check for metadata
        assert "Agency1,sesh1,prog1,,,False,th_" in line

    # Check for empty feedback
    csv_obj = next(csv.DictReader(mock_csv_file.getvalue().splitlines()))
    assert csv_obj["Feedback Scores"] == ""
    assert csv_obj["Feedback Comments"] == ""


def test_one_feedback():
    threads = create_threads(1)
    assistant_step = threads[0].steps[1]
    assistant_step.scores = [
        Score(
            name="user-feedback",
            type="HUMAN",
            value=1.0,
            step_id=assistant_step.id,
            dataset_experiment_item_id=None,
            comment="Good job",
            tags=None,
        )
    ]

    qa_rows = convert_to_qa_rows("Test_Project_1234ABC", threads)
    mock_csv_file = StringIO()
    save_csv(qa_rows, mock_csv_file)
    csv_obj = next(csv.DictReader(mock_csv_file.getvalue().splitlines()))
    assert csv_obj["Feedback Scores"] == "1.0"
    assert csv_obj["Feedback Comments"] == "Good job"


def test_multiple_feedback():
    threads = create_threads(1)
    assistant_step = threads[0].steps[1]
    assistant_step.scores = [
        Score(
            name="user-feedback",
            type="HUMAN",
            value=1.0,
            step_id=assistant_step.id,
            dataset_experiment_item_id=None,
            comment="",
            tags=None,
        ),
        Score(
            name="user-feedback",
            type="HUMAN",
            value=0.0,
            step_id=assistant_step.id,
            dataset_experiment_item_id=None,
            comment="Needs improvement",
            tags=None,
        ),
    ]

    qa_rows = convert_to_qa_rows("Test_Project_1234ABC", threads)
    mock_csv_file = StringIO()
    save_csv(qa_rows, mock_csv_file)
    csv_obj = next(csv.DictReader(mock_csv_file.getvalue().splitlines()))
    assert csv_obj["Feedback Scores"] == "[1.0, 0.0]"
    assert csv_obj["Feedback Comments"] == "['', 'Needs improvement']"

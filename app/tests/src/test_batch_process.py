import pytest

from src import chat_engine
from src.batch_process import _process_question, batch_process
from src.chat_engine import OnMessageResult
from src.db.models.document import Subsection
from tests.src.db.models.factories import ChunkFactory


@pytest.fixture
def engine():
    return chat_engine.create_engine("ca-edd-web")


@pytest.fixture
def sample_csv(tmp_path):
    csv_content = (
        "question,metadata\n" "What is AI?,some metadata\n" "Second question,other metadata"
    )
    csv_path = tmp_path / "questions.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)


@pytest.fixture
def invalid_csv(tmp_path):
    csv_content = "not_question\nWhat is AI?"
    csv_path = tmp_path / "invalid_questions.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)


@pytest.mark.asyncio
async def test_batch_process_invalid(invalid_csv, engine):
    engine = chat_engine.create_engine("ca-edd-web")
    with pytest.raises(ValueError, match="CSV file must contain a 'question' column."):
        await batch_process(invalid_csv, engine)


@pytest.mark.asyncio
async def test_batch_process(monkeypatch, sample_csv, engine):
    def mock__process_question(question, engine):
        if question == "What is AI?":
            return {"answer": "Answer to What is AI?", "field_2": "value_2"}
        return {"answer": "Answer to Second question", "field_3": "value_3"}

    monkeypatch.setattr("src.batch_process._process_question", mock__process_question)

    result = await batch_process(sample_csv, engine)
    with open(result) as f:
        assert f.read() == (
            "question,metadata,answer,field_2,field_3\n"
            "What is AI?,some metadata,Answer to What is AI?,value_2,\n"
            "Second question,other metadata,Answer to Second question,,value_3\n"
        )


def test_process_question(monkeypatch, engine):
    chunk = ChunkFactory.build()
    subsection_text = chunk.content[: int(len(chunk.content) / 2)]
    mock_result = OnMessageResult(
        response="Answer to question.(citation-1)",
        subsections=[Subsection("citation-1", chunk, subsection_text)],
        chunks_with_scores=[],
        system_prompt="",
    )

    monkeypatch.setattr(engine, "on_message", lambda question, chat_history: mock_result)
    assert _process_question("What is AI?", engine) == {
        "answer": "Answer to question.(citation-1)",
        "citation_1_name": mock_result.subsections[0].chunk.document.name,
        "citation_1_headings": " > ".join(mock_result.subsections[0].text_headings),
        "citation_1_source": mock_result.subsections[0].chunk.document.source,
        "citation_1_text": subsection_text,
    }

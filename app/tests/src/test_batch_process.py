import pytest

from src import chat_engine
from src.batch_process import batch_process


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
        return {"answer": f"Answer to {question}", "field_2": "value_2"}

    monkeypatch.setattr("src.batch_process._process_question", mock__process_question)

    result = await batch_process(sample_csv, engine)
    with open(result) as f:
        assert f.read() == (
            "question,metadata,answer,field_2\n"
            "What is AI?,some metadata,Answer to What is AI?,value_2\n"
            "Second question,other metadata,Answer to Second question,value_2\n"
        )

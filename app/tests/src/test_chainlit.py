from unittest.mock import MagicMock

from src import chainlit, chat_engine
from src.chainlit import _get_retrieval_metadata, get_raw_chat_history
from src.chat_engine import OnMessageResult
from src.db.models.document import Subsection
from src.generate import PROMPT


def test_url_query_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")

    url = "https://example.com/chat/?engine=guru-snap&llm=gpt-4o&retrieval_k=3&someunknownparam=42"
    query_values = chainlit.url_query_values(url)
    engine_id = query_values.pop("engine")
    assert engine_id == "guru-snap"

    engine = chat_engine.create_engine(engine_id)
    input_widgets = chainlit._init_chat_settings(engine, query_values)
    assert len(input_widgets) == len(engine.user_settings)

    # Only 1 query parameter remains
    assert len(query_values) == 1
    assert query_values["someunknownparam"] == "42"


def test__get_retrieval_metadata(chunks_with_scores):
    system_prompt = "Some system prompt"
    chunks = [chunk_with_score.chunk for chunk_with_score in chunks_with_scores]
    subsections = [Subsection(chunk.id, chunk, chunk.content) for chunk in chunks]
    result = OnMessageResult("Some response", system_prompt, chunks_with_scores, subsections)

    metadata = _get_retrieval_metadata(result)
    assert metadata["system_prompt"] == system_prompt
    assert metadata["chunks"] == [
        {
            "document.name": chunks_with_scores[0].chunk.document.name,
            "chunk.id": str(chunks_with_scores[0].chunk.id),
            "score": chunks_with_scores[0].score,
        },
        {
            "document.name": chunks_with_scores[1].chunk.document.name,
            "chunk.id": str(chunks_with_scores[1].chunk.id),
            "score": chunks_with_scores[1].score,
        },
        {
            "document.name": chunks_with_scores[2].chunk.document.name,
            "chunk.id": str(chunks_with_scores[2].chunk.id),
            "score": chunks_with_scores[2].score,
        },
    ]
    assert metadata["subsections"] == [
        {
            "id": citations.id,
            "chunk.id": str(citations.chunk.id),
            "document.name": citations.chunk.document.name,
            "headings": citations.chunk.headings,
            "text": citations.text,
        }
        for citations in subsections
    ]


def test__get_raw_chat_history():
    clMessage1 = MagicMock()
    clMessage2 = MagicMock()
    clMessage3 = MagicMock()
    clMessage1.configure_mock(
        content="CA EDD Web Chat Engine started ",
        metadata={
            "engine": "ca-edd-web",
            "settings": {
                "llm": "gpt-4o",
                "retrieval_k": 50.0,
                "retrieval_k_min_score": -1.0,
                "chunks_shown_max_num": 8.0,
                "chunks_shown_min_score": -1.0,
                "system_prompt": PROMPT,
            },
        },
        author="backend",
        type="assistant_message",
    )
    clMessage2.configure_mock(
        content="can you tell me about income eligibility?",
        author="User",
        type="user_message",
    )
    clMessage3.configure_mock(
        content="<div>To be eligible for unemployment benefits, you need to have earned enough wages during a specific 12-month period called the base period (citation-46). <p>For Disability Insurance, you must have earned at least $300 in wages that were subject to State Disability Insurance (SDI) deductions (citation-123). For Paid Family Leave, you also need to have earned at least $300 with SDI deductions during your base period (citation-129).</p> If you are applying for an overpayment waiver, your average monthly income must be less than or equal to the amounts in the Family Income Level Table (citation-118).</div>",
        metadata={
            "system_prompt": PROMPT,
            "raw_response": "To be eligible for unemployment benefits, you need to have earned enough wages during a specific 12-month period called the base period (citation-46). For Disability Insurance, you must have earned at least $300 in wages that were subject to State Disability Insurance (SDI) deductions (citation-123). For Paid Family Leave, you also need to have earned at least $300 with SDI deductions during your base period (citation-129). If you are applying for an overpayment waiver, your average monthly income must be less than or equal to the amounts in the Family Income Level Table (citation-118).",
        },
        author="Decision support tool",
        type="assistant_message",
    )
    message = [clMessage1, clMessage2, clMessage3]

    assert get_raw_chat_history(message) == [
        {"role": "assistant", "content": "CA EDD Web Chat Engine started "},
        {"role": "user", "content": "can you tell me about income eligibility?"},
        {
            "role": "assistant",
            "content": "To be eligible for unemployment benefits, you need to have earned enough wages during a specific 12-month period called the base period (citation-46). For Disability Insurance, you must have earned at least $300 in wages that were subject to State Disability Insurance (SDI) deductions (citation-123). For Paid Family Leave, you also need to have earned at least $300 with SDI deductions during your base period (citation-129). If you are applying for an overpayment waiver, your average monthly income must be less than or equal to the amounts in the Family Income Level Table (citation-118).",
        },
    ]

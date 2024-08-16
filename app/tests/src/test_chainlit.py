from src import chainlit, chat_engine
from src.chainlit import _get_retrieval_metadata


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
    assert _get_retrieval_metadata(chunks_with_scores) == {
        "chunks": [
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
    }

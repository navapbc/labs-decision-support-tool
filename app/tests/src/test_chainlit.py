from src import chainlit, chat_engine
from src.chainlit import _get_retrieval_metadata
from src.chat_engine import OnMessageResult
from src.db.models.document import ChunkWithSubsection


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
    subsections = [ChunkWithSubsection(chunk.id, chunk, chunk.content) for chunk in chunks]
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
            "text": citations.subsection,
        }
        for citations in subsections
    ]

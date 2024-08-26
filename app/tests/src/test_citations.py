from src.citations import add_citations, get_context_for_prompt
from src.db.models.document import ChunkWithScore
from tests.src.db.models.factories import ChunkFactory


def test_get_context_for_prompt():
    assert get_context_for_prompt([]) == ""

    chunks_with_score = [
        ChunkWithScore(ChunkFactory.build(), 0.90),
        ChunkWithScore(ChunkFactory.build(), 0.90),
    ]
    assert (
        get_context_for_prompt(chunks_with_score)
        == f"Citation: chunk-0 \nContent: {chunks_with_score[0].chunk.content}\n\nCitation: chunk-1 \nContent: {chunks_with_score[1].chunk.content}"
    )


def test_add_citations():
    assert add_citations("This is a citation (chunk-0)", []) == "This is a citation (chunk-0)</br>"

    chunks = ChunkFactory.build_batch(2)
    assert all(
        text in add_citations("This is a citation (chunk-0) and another (chunk-1).", chunks)
        for text in [
            "This is a citation",
            chunks[0].document.name,
            "and another",
            chunks[1].document.name,
        ]
    )

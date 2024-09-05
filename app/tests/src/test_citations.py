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
        == f"Citation: chunk-0\nDocument name: {chunks_with_score[0].chunk.document.name}\nContent: {chunks_with_score[0].chunk.content}\n\nCitation: chunk-1\nDocument name: {chunks_with_score[1].chunk.document.name}\nContent: {chunks_with_score[1].chunk.content}"
    )


def test_add_citations():
    assert add_citations("This is a citation (chunk-0)", []) == "This is a citation (chunk-0)"

    chunks = ChunkFactory.build_batch(2)
    assert (
        add_citations("This is a citation (chunk-0) and another (chunk-1).", chunks)
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )
    """"
    assert all(
        text in add_citations("This is a citation (chunk-0) and another (chunk-1).", chunks)
        for text in [
            "This is a citation",
            chunks[0].document.name,
            "and another",
            chunks[1].document.name,
        ]
    )
    """

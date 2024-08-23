from src.citations import add_citations
from tests.src.db.models.factories import ChunkFactory


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

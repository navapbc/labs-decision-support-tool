from src.citations import add_citations
from tests.src.db.models.factories import ChunkFactory


def test_add_citations():
    assert add_citations("This is a citation (chunk-0)", []) == "This is a citation (chunk-0)"

    chunks = ChunkFactory.build_batch(2)
    assert add_citations("This is a citation (chunk-0) and another (chunk-1).", chunks) == (
        f"This is a citation ([{chunks[0].document.name}]({chunks[0].document}))"
        f" and another ([{chunks[1].document.name}]({chunks[1].document}))."
    )

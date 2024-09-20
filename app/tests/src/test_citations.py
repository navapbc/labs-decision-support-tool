from src.citations import add_citations, get_context_for_prompt
from src.db.models.document import ChunkWithScore
from tests.src.db.models.factories import ChunkFactory


def test_get_context_for_prompt():
    assert get_context_for_prompt([]) == ""

    chunks = ChunkFactory.build_batch(2)
    assert (
        get_context_for_prompt(chunks)
        == f"Citation: citation-0\nDocument name: {chunks[0].document.name}\nHeadings: {" > ".join(chunks[0].headings)}\nContent: {chunks[0].content}\n\nCitation: citation-1\nDocument name: {chunks[1].document.name}\nHeadings: {" > ".join(chunks[1].headings)}\nContent: {chunks[1].content}"
    )


def test_add_citations():
    assert add_citations("This is a citation (citation-0)", []) == "This is a citation (citation-0)"

    chunks = ChunkFactory.build_batch(2)
    assert (
        add_citations("This is a citation (citation-0) and another (citation-1).", chunks)
        == "This is a citation <sup><a href='#'>1</a>&nbsp;</sup> and another <sup><a href='#'>2</a>&nbsp;</sup>."
    )

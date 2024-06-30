from src.format import format_guru_cards
from tests.src.db.models.factories import ChunkFactory


def test_format_guru_cards():
    chunks = ChunkFactory.build_batch(3)
    html = format_guru_cards(chunks)
    assert "accordion-1" in html
    assert "Related Guru cards" in html
    assert chunks[0].document.name in html
    assert chunks[0].document.content in html
    assert chunks[1].document.name in html
    assert chunks[1].document.content in html
    assert chunks[2].document.name in html
    assert chunks[2].document.content in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(chunks)
    assert "accordion-1" not in next_html
    assert "accordion-4" in next_html

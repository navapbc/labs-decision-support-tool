from typing import Sequence

from src.db.models.document import ChunkWithScore

# We need a unique identifier for each accordion,
# even across multiple calls to this function
_accordion_id = 0


def format_guru_cards(chunks_with_scores: Sequence[ChunkWithScore]) -> str:
    cards_html = ""
    for chunk_with_score in chunks_with_scores:
        global _accordion_id
        _accordion_id += 1
        similarity_score = f"<p>Similarity Score: {str(chunk_with_score.score)}</p>"
        document = chunk_with_score.chunk.document
        cards_html += f"""
<div class="usa-accordion" id=accordion-{_accordion_id}>
    <h4 class="usa-accordion__heading">
        <button
            type="button"
            class="usa-accordion__button"
            aria-expanded="false"
            aria-controls="a-{_accordion_id}"
            >
            <a href='https://link/to/guru_card'>{document.name}</a>
        </button>
    </h4>
    <div id="a-{_accordion_id}" class="usa-accordion__content usa-prose" hidden>
        <p>Summary: {document.content}</p>
        {similarity_score}
    </div>
</div>"""
    return "<h3>Related Guru cards</h3>" + cards_html

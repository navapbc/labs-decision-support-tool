import logging
import random
import re
from collections import OrderedDict
from typing import Sequence

from src.db.models.document import ChunkWithScore, Document

logger = logging.getLogger(__name__)

# We need a unique identifier for each accordion,
# even across multiple calls to this function.
# Choose a random number to avoid id collisions when hotloading the app during development.
_accordion_id = random.randint(0, 1000000)


def format_guru_cards(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
) -> str:
    cards_html = ""
    for chunk_with_score in chunks_with_scores[:docs_shown_max_num]:
        document = chunk_with_score.chunk.document
        if chunk_with_score.score < docs_shown_min_score:
            logger.info(
                "Skipping chunk with score less than %f: %s",
                docs_shown_min_score,
                document.name,
            )
            continue

        global _accordion_id
        _accordion_id += 1
        similarity_score = f"<p>Similarity Score: {str(chunk_with_score.score)}</p>"
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


def _get_bem_documents_to_show(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: list[ChunkWithScore],
) -> OrderedDict[Document, list[ChunkWithScore]]:
    chunks_with_scores.sort(key=lambda c: c.score, reverse=True)

    # Build a dictionary of documents with their associated chunks,
    # Ordered by the highest score of each chunk associated with the document
    documents: OrderedDict[Document, list[ChunkWithScore]] = OrderedDict()
    for chunk_with_score in chunks_with_scores[:docs_shown_max_num]:
        document = chunk_with_score.chunk.document
        if chunk_with_score.score < docs_shown_min_score:
            logger.info(
                "Skipping chunk with score less than %f: %s",
                docs_shown_min_score,
                chunk_with_score.chunk.document.name,
            )
            continue

        if document in documents:
            documents[document].append(chunk_with_score)
        else:
            documents[document] = [chunk_with_score]

    return documents


def _format_bem_title(bem_title: str) -> str:
    # Remove all caps, but keep "BEM" capitalized
    bem_title = bem_title.title()
    bem_title = bem_title.replace("Bem", "BEM")

    # Extract the BEM number ("100", "235C", etc.) and use that to generate link
    bem_number_search = re.search(r"\b(\d{3}[ABC]?)\b", bem_title)
    bem_number = bem_number_search.group(1) if bem_number_search else None
    if bem_number:
        bem_title = bem_title.replace(
            f"BEM {bem_number}",
            f'<a href="https://dhhs.michigan.gov/olmweb/ex/BP/Public/BEM/{bem_number}.pdf">BEM {bem_number}</a>',
        )

    return bem_title


def format_bem_documents(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: list[ChunkWithScore],
) -> str:
    documents = _get_bem_documents_to_show(
        docs_shown_max_num, docs_shown_min_score, chunks_with_scores
    )

    html = "<h3>Source(s)</h3><ul>\n"

    for document in documents:
        html += f"<li>{_format_bem_title(document.name)}<ol>\n"

        for index, chunk in enumerate(documents[document], start=1):
            html += f"<li>Citation #{index} (score: {chunk.score})</li>\n"

        html += "</ol></li>\n"

    html += "</ul>"

    return html

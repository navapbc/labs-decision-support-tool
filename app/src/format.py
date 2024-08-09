import logging
import random
from typing import Sequence

from src.db.models.document import ChunkWithScore, Document, DocumentWithMaxScore

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
        cards_html += format_to_accordion_html(document=document, score=chunk_with_score.score)
    return "<h3>Related Guru cards</h3>" + cards_html


def _get_bem_documents_to_show(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
) -> Sequence[DocumentWithMaxScore]:
    # Build a deduplicated list of documents with the max score
    # of all chunks associated with the document.
    documents_with_scores: list[DocumentWithMaxScore] = []
    for chunk_with_score in chunks_with_scores:
        if chunk_with_score.score >= docs_shown_min_score:
            document = chunk_with_score.chunk.document
            existing_doc = next(
                (d for d in documents_with_scores if d.document == document),
                None,
            )
            if existing_doc:
                existing_doc.max_score = max(existing_doc.max_score, chunk_with_score.score)
            else:
                documents_with_scores.append(DocumentWithMaxScore(document, chunk_with_score.score))

    # Sort the list by score
    documents_with_scores.sort(key=lambda d: d.max_score, reverse=True)

    # Only return the top docs_shown_max_num documents
    return documents_with_scores[:docs_shown_max_num]


def format_bem_documents(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
) -> str:
    documents = _get_bem_documents_to_show(
        docs_shown_max_num, docs_shown_min_score, chunks_with_scores
    )
    pdf_chunks = ""
    for chunk_with_score in documents:
        document = chunk_with_score.document
        if chunk_with_score.max_score < docs_shown_min_score:
            logger.info(
                "Skipping chunk with score less than %f: %s",
                docs_shown_min_score,
                document.name,
            )
            continue
        pdf_chunks += format_to_accordion_html(document=document, score=chunk_with_score.max_score)

    return "<h3>Source(s)</h3>" + pdf_chunks


def format_to_accordion_html(document: Document, score: float) -> str:
    global _accordion_id
    _accordion_id += 1
    similarity_score = f"<p>Similarity Score: {str(score)}</p>"

    return f"""
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
            <p>Summary: {document.content.strip() if document.content else ""}</p>
            {similarity_score}
        </div>
    </div>"""

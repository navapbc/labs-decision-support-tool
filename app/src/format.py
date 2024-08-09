import logging
import random
from typing import OrderedDict, Sequence

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
        cards_html += _format_to_accordion_html(document=document, score=chunk_with_score.score)
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


def format_bem_documents(
    docs_shown_max_num: int,
    docs_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
) -> str:
    documents = _get_bem_documents_to_show(
        docs_shown_max_num, docs_shown_min_score, chunks_with_scores
    )

    return _format_to_accordion_group_html(documents)


def _format_to_accordion_html(document: Document, score: float) -> str:
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
                <a href='https://link'>{document.name}</a>
            </button>
        </h4>
        <div id="a-{_accordion_id}" class="usa-accordion__content usa-prose" hidden>
            {"<p>Summary: " + document.content.strip() if document.content else ""}</p>
            {similarity_score}
        </div>
    </div>"""


def _format_to_accordion_group_html(documents: OrderedDict[Document, list[ChunkWithScore]]) -> str:
    global _accordion_id
    _accordion_id += 1
    print(documents)
    html = "<h3>Source(s)</h3>"
    for document in documents:
        internal_citation=""
        for index, chunk in enumerate(documents[document], start=1):
            internal_citation += f"""<div id="a-{_accordion_id}" class="usa-accordion__content usa-prose margin-left-2 border-left-1 border-base-lighter" hidden>
                    <h4>Citation #{index} (score: {chunk.score})</h4>
                    {f"<p>Summary: {chunk.chunk.content.strip()} </p>" if chunk.chunk.content else ""}
                    <p>Similarity Score: {str(chunk.score)}</p>
                </div>"""
        
        html+= f"""
            <div class="usa-accordion" id=accordion-{_accordion_id}>
                <h4 class="usa-accordion__heading">
                    <button
                        type="button"
                        class="usa-accordion__button"
                        aria-expanded="false"
                        aria-controls="a-{_accordion_id}"
                        >
                        <a href='https://link'>{document.name}</a>
                    </button>
                </h4>
                {internal_citation}
            </div>"""
    return html
import logging
import random
import re
from typing import Match, OrderedDict, Sequence

import markdown

from src.citations import CITATION_PATTERN, remap_citation_ids
from src.db.models.document import Chunk, ChunkWithScore, ChunkWithSubsection, Document
from src.citations import (
    combine_citations_by_document,
    reify_citations_with_scores,
    split_into_subsections,
)
from src.db.models.document import Chunk, ChunkWithScore, Document
from src.util.bem_util import get_bem_url, replace_bem_with_link

logger = logging.getLogger(__name__)

# We need a unique identifier for each accordion,
# even across multiple calls to this function.
# Choose a random number to avoid id collisions when hotloading the app during development.
_accordion_id = random.randint(0, 1000000)


def format_guru_cards(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[ChunkWithSubsection],
    raw_response: str,
) -> str:
    response_with_citations = reify_citations(raw_response, subsections)

    cards_html = ""
    for chunk_with_score in chunks_with_scores[:chunks_shown_max_num]:
        document = chunk_with_score.chunk.document
        if chunk_with_score.score < chunks_shown_min_score:
            logger.info(
                "Skipping chunk with score less than %f: %s",
                chunks_shown_min_score,
                document.name,
            )
            continue
        cards_html += _format_to_accordion_html(document=document, score=chunk_with_score.score)

    return response_with_citations + "<h3>Related Guru cards</h3>" + cards_html


def _get_bem_documents_to_show(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: list[ChunkWithScore],
) -> OrderedDict[Document, list[ChunkWithScore]]:
    chunks_with_scores.sort(key=lambda c: c.score, reverse=True)

    # Build a dictionary of documents with their associated chunks,
    # Ordered by the highest score of each chunk associated with the document
    documents: OrderedDict[Document, list[ChunkWithScore]] = OrderedDict()
    for chunk_with_score in chunks_with_scores[:chunks_shown_max_num]:
        document = chunk_with_score.chunk.document
        if chunk_with_score.score < chunks_shown_min_score:
            logger.info(
                "Skipping chunk with score less than %f: %s",
                chunks_shown_min_score,
                chunk_with_score.chunk.document.name,
            )
            continue

        if document in documents:
            documents[document].append(chunk_with_score)
        else:
            documents[document] = [chunk_with_score]

    return documents


def to_html(text: str) -> str:
    # markdown expects '\n' before the start of a list
    corrected_text = re.sub(r"^- ", "\n- ", text, flags=re.MULTILINE, count=1)
    return markdown.markdown(corrected_text)


def format_bem_subsections(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[ChunkWithSubsection],
    raw_response: str,
) -> str:
    global _accordion_id

    remapped_citations = remap_citation_ids(subsections, raw_response)
    citations_html = ""
    for _orig_citation_id, citation in remapped_citations.items():
        _accordion_id += 1
        chunk = citation.chunk
        subsection = citation.subsection

    citations_by_document = combine_citations_by_document(remapped_citations)
    for document, chunks_in_doc in citations_by_document.items():
        citation_body = ""
        citation_numbers = []
        for chunk_in_doc in chunks_in_doc:
            for citation, grouped_citations in chunk_in_doc.items():
                _accordion_id += 1
                for citation_item in grouped_citations:
                    for citation_number, subsection in citation_item.items():
                        citation_numbers.append(f"{citation_number}")
                        citation_body += f'<div>Citation #{citation_number}: </div><div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">{subsection}</div>'

                formatted_citation_body = to_html(replace_bem_with_link(citation_body))
                bem_url_for_page = get_bem_url(document.name)
                if citation.page_number:
                    bem_url_for_page += "#page=" + str(citation.page_number)

                citation_headings = (
                    "<p>" + " → ".join(citation.headings) + "</p>" if citation.headings else ""
                )
                citation_link = (
                    (
                        f"<p><a href={bem_url_for_page!r}>Open document to page {citation.page_number}</a></p>"
                    )
                    if citation.page_number
                    else ""
                )

        citations_html += f"""
        <div class="usa-accordion" id=accordion-{_accordion_id}>
            <h4 class="usa-accordion__heading">
                <button
                    type="button"
                    class="usa-accordion__button"
                    aria-expanded="false"
                    aria-controls="a-{_accordion_id}">
                    {",".join(citation_numbers)}. {document.name}
                </button>
            </h4>
            <div id="a-{_accordion_id}" class="usa-accordion__content usa-prose" hidden>
                {citation_headings}
                {formatted_citation_body}
                {citation_link}
            </div>
        </div>"""

    # This heading is important to prevent Chainlit from embedding citations_html
    # as the next part of a a list in response_with_citations
    response_with_citations = to_html(_add_citation_links(raw_response, remapped_citations))
    if citations_html:
        return (
            "<div>"
            + response_with_citations
            + "</div><h3>Source(s)</h3><div>"
            + citations_html
            + "</div>"
        )
    return "<div>" + response_with_citations + "</div>"


def format_bem_documents(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[ChunkWithSubsection],
    raw_response: str,
) -> str:
    response_with_citations = reify_citations(raw_response, subsections)

    documents = _get_bem_documents_to_show(
        chunks_shown_max_num, chunks_shown_min_score, list(chunks_with_scores)
    )

    return response_with_citations + _format_to_accordion_group_html(documents)


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
            "<p>" + " → ".join(chunk.headings) + "</p>" if chunk.headings else ""
            {"<p>" + document.content.strip() if document.content else ""}</p>
            {similarity_score}
        </div>
    </div>"""


def _format_to_accordion_group_html(documents: OrderedDict[Document, list[ChunkWithScore]]) -> str:
    global _accordion_id
    html = ""
    citation_number = 1
    for document in documents:
        citations = ""
        _accordion_id += 1

        citation_number_start = citation_number

        for chunk_with_score in documents[document]:
            chunk = chunk_with_score.chunk

            formatted_chunk = _add_ellipses(chunk)
            formatted_chunk = replace_bem_with_link(formatted_chunk)

            # Adjust markdown for lists so Chainlit renders correctly
            formatted_chunk = re.sub("^ - ", "- ", formatted_chunk, flags=re.MULTILINE)
            if formatted_chunk.startswith("- "):
                formatted_chunk = "\n" + formatted_chunk

            bem_url_for_page = get_bem_url(document.name)
            if chunk.page_number:
                bem_url_for_page += "#page=" + str(chunk.page_number)

            citation_heading = f"<h4>Citation {citation_number}:</h4>"
            chunk_headings = "<p>" + " → ".join(chunk.headings) + "</p>" if chunk.headings else ""
            citation_body = f'<div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">{formatted_chunk}</div>'
            citation_link = (
                (
                    f"<p><a href={bem_url_for_page!r}>Open document to page {chunk.page_number}</a></p>"
                )
                if chunk.page_number
                else ""
            )
            citations += citation_heading + chunk_headings + citation_body + citation_link

            citation_number += 1

        citation_number_end = citation_number - 1
        citation_range = (
            f"Citation {citation_number_start}"
            if citation_number_start == citation_number_end
            else f"Citations {citation_number_start} - {citation_number_end}"
        )

        html += f"""
            <div class="usa-accordion" id=accordion-{_accordion_id}>
                <h4 class="usa-accordion__heading">
                    <button
                        type="button"
                        class="usa-accordion__button"
                        aria-expanded="false"
                        aria-controls="a-{_accordion_id}"
                        >
                        <a href="{get_bem_url(document.name)}">{document.name}</a> ({citation_range})
                    </button>
                </h4>
                <div id="a-{_accordion_id}" class="usa-accordion__content usa-prose" hidden>
                {citations}
                </div>
            </div>"""  # noqa: B907

    return "\n<h3>Source(s)</h3>" + html if html else ""


def _add_ellipses(chunk: Chunk) -> str:
    chunk_content = chunk.content
    if chunk.num_splits != 0:
        if chunk.split_index == 0:
            return f"{chunk_content} ..."
        elif chunk.split_index == chunk.num_splits:
            return f"... {chunk_content}"
        else:
            return f"... {chunk_content} ..."
    return chunk_content


def reify_citations(response: str, subsections: Sequence[ChunkWithSubsection]) -> str:
    remapped_citations = remap_citation_ids(subsections, response)
    return _add_citation_links(response, remapped_citations)


_footnote_id = random.randint(0, 1000000)
_footnote_index = 0


def _add_citation_links(response: str, remapped_citations: dict[str, ChunkWithSubsection]) -> str:
    global _footnote_id
    _footnote_id += 1
    footnote_list = []

    # Replace (citation-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        matched_text = match.group(1)
        global _footnote_index
        _footnote_index += 1
        # Leave a citation for chunks that don't exist alone
        citation_id = matched_text  # .removeprefix("citation-")
        if citation_id not in remapped_citations:
            logger.warning(
                "LLM generated a citation for a reference (%s) that doesn't exist.", citation_id
            )
            return f"({matched_text})"

        chunk = remapped_citations[citation_id].chunk
        bem_link = get_bem_url(chunk.document.name) if "BEM" in chunk.document.name else "#"
        bem_link += "#page=" + str(chunk.page_number) if chunk.page_number else ""
        citation = f"<sup><a href={bem_link!r}>{remapped_citations[citation_id].id}</a>&nbsp;</sup>"
        footnote_list.append(
            f"<a style='text-decoration:none' href={bem_link!r}><sup id={_footnote_id!r}>{_footnote_index}. {chunk.document.name}</sup></a>"
        )
        return citation

    # Replace all instances of (citation-<index>) with an html link on superscript "<index>"
    added_citations = re.sub(CITATION_PATTERN, replace_citation, response)

    # For now, don't show footnote list
    return added_citations  # + "</br>" + "</br>".join(footnote_list)

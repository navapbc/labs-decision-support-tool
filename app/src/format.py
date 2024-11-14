import logging
import random
import re
from collections import defaultdict
from itertools import groupby
from typing import Match, OrderedDict, Sequence

import markdown

from src.citations import CITATION_PATTERN, remap_citation_ids
from src.db.models.document import Chunk, ChunkWithScore, Document, Subsection
from src.util.bem_util import get_bem_url, replace_bem_with_link

logger = logging.getLogger(__name__)

# We need a unique identifier for each accordion,
# even across multiple calls to this function.
# Choose a random number to avoid id collisions when hotloading the app during development.
_accordion_id = random.randint(0, 1000000)


class FormattingConfig:
    "Default formatting configuration"
    def __init__(self) -> None:
        self.add_citation_link_per_subsection = False

    def return_citation_link(self, chunk: Chunk) -> str:
        if chunk.document.source:
            return f"<p>Source: <a href={chunk.document.source!r}>{chunk.document.source}</a></p>"
        return ""

    def get_superscript_link(self, chunk: Chunk) -> str:
        return chunk.document.source if chunk.document.source else "#"

    def build_accordion_body(self, citation_body: str) -> str:
        return to_html(citation_body)


class BemFormattingConfig(FormattingConfig):
    "BEM-specific formatting configuration"
    def __init__(self) -> None:
        self.add_citation_link_per_subsection = True

    def return_citation_link(self, chunk: Chunk) -> str:
        bem_url_for_page = get_bem_url(chunk.document.name)
        if chunk.page_number:
            bem_url_for_page += "#page=" + str(chunk.page_number)
        return (
            f"<p><a href={bem_url_for_page!r}>Open document to page {chunk.page_number}</a></p>"
            if chunk.page_number
            else ""
        )

    def get_superscript_link(self, chunk: Chunk) -> str:
        link = get_bem_url(chunk.document.name) if "BEM" in chunk.document.name else "#"
        link += "#page=" + str(chunk.page_number) if chunk.page_number else ""
        return link

    def build_accordion_body(self, citation_body: str) -> str:
        return to_html(replace_bem_with_link(citation_body))


def format_guru_cards(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[Subsection],
    raw_response: str,
) -> str:
    response_with_citations = reify_citations(raw_response, subsections, FormattingConfig())

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
    subsections: Sequence[Subsection],
    raw_response: str,
) -> str:
    return build_accordions(
        subsections=subsections, raw_response=raw_response, config=BemFormattingConfig()
    )


def build_accordions(
    subsections: Sequence[Subsection], raw_response: str, config: FormattingConfig
) -> str:
    global _accordion_id

    remapped_citations = remap_citation_ids(subsections, raw_response)
    citations_html = ""
    citations_by_document = _group_by_document_and_chunks(remapped_citations)
    for document, chunks_in_doc in citations_by_document.items():
        citation_numbers = []
        citation_body = ""
        rendered_heading = ""
        for chunk, subsection_list in chunks_in_doc:
            citation_headings = (
                _get_breadcrumb_html(chunk.headings, chunk.document.name) if chunk.headings else ""
            )
            # only show headings if they are different
            if rendered_heading != citation_headings:
                citation_body += f"<b>{citation_headings}</b>"
                rendered_heading = citation_headings

            citation_link = config.return_citation_link(chunk)
            for chunk_subsection in subsection_list:
                citation_numbers.append(chunk_subsection.id)
                citation_body += (
                    f"<div>Citation #{chunk_subsection.id}: </div>"
                    f'<div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">{to_html(chunk_subsection.text)}</div>'
                )
                if config.add_citation_link_per_subsection:
                    # generated citation links for BEM redirect to specific pages
                    citation_body += f"<div>{citation_link}</div>"

        if not config.add_citation_link_per_subsection:
            # return source link once
            citation_body += f"<div>{citation_link}</div>"

        _accordion_id += 1
        formatted_citation_body = config.build_accordion_body(citation_body)
        citations_html += f"""
        <div class="usa-accordion" id=accordion-{_accordion_id}>
            <h4 class="usa-accordion__heading">
                <button
                    type="button"
                    class="usa-accordion__button"
                    aria-expanded="false"
                    aria-controls="a-{_accordion_id}">
                    {",".join(citation_numbers)}. {document.dataset}: {document.name}
                </button>
            </h4>
            <div id="a-{_accordion_id}" class="usa-accordion__content usa-prose" hidden>
                {formatted_citation_body}
            </div>
        </div>"""

    # This heading is important to prevent Chainlit from embedding citations_html
    # as the next part of a a list in response_with_citations
    response_with_citations = to_html(_add_citation_links(raw_response, remapped_citations, config))
    if citations_html:
        return (
            "<div>"
            + response_with_citations
            + "</div><h3>Source(s)</h3><div>"
            + citations_html
            + "</div>"
        )
    return "<div>" + response_with_citations + "</div>"


def format_web_subsections(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[Subsection],
    raw_response: str,
) -> str:
    return build_accordions(
        subsections=subsections, raw_response=raw_response, config=FormattingConfig()
    )


def _get_breadcrumb_html(headings: Sequence[str] | None, document_name: str) -> str:
    if not headings:
        return "<div>&nbsp;</div>"

    # Skip empty headings
    headings = [h for h in headings if h]

    # Only show last two headings
    headings = headings[-2:]

    # Don't repeat document name
    if headings[0] == document_name:
        headings = headings[1:]

    return f"<div><b>{' → '.join(headings)}</b></div>"


ChunkWithCitation = tuple[Chunk, Sequence[Subsection]]


def _group_by_document_and_chunks(
    remapped_citations: dict[str, Subsection]
) -> dict[Document, list[ChunkWithCitation]]:
    """
    Group the chunks by document and nests the values of the citation number and subsection string.
    Argument `remapped_citations` maps original citation_id (used in the LLM generated response) to Subsection
    """
    # Group the input citations by chunk then by document
    by_chunk = groupby(remapped_citations.values(), key=lambda t: t.chunk)
    by_doc = groupby(by_chunk, key=lambda t: t[0].document)

    # Create output dictionary with structure {Document: [(Chunk, [Subsection])]}
    citations_by_document: dict[Document, list[ChunkWithCitation]] = defaultdict(list)
    for doc, chunk_list in by_doc:
        for chunk, subsection_list in chunk_list:
            citations_by_document[doc].append((chunk, list(subsection_list)))

    return citations_by_document


def format_bem_documents(
    chunks_shown_max_num: int,
    chunks_shown_min_score: float,
    chunks_with_scores: Sequence[ChunkWithScore],
    subsections: Sequence[Subsection],
    raw_response: str,
) -> str:
    response_with_citations = reify_citations(raw_response, subsections, BemFormattingConfig())

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


def reify_citations(
    response: str, subsections: Sequence[Subsection], config: FormattingConfig
) -> str:
    remapped_citations = remap_citation_ids(subsections, response)
    return _add_citation_links(response, remapped_citations, config)


_footnote_id = random.randint(0, 1000000)
_footnote_index = 0


def _add_citation_links(
    response: str, remapped_citations: dict[str, Subsection], config: FormattingConfig
) -> str:
    global _footnote_id
    _footnote_id += 1
    footnote_list = []

    # Replace (citation-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        citation_id = match.group(1)
        # Remove citation for chunks that don't exist alone
        if citation_id not in remapped_citations:
            logger.error(
                "LLM generated a citation for a reference (%s) that doesn't exist.", citation_id
            )
            return ""

        chunk = remapped_citations[citation_id].chunk
        link = config.get_superscript_link(chunk)

        citation = f"<sup><a href={link!r}>{remapped_citations[citation_id].id}</a>&nbsp;</sup>"

        global _footnote_index
        _footnote_index += 1
        footnote_list.append(
            f"<a style='text-decoration:none' href={link!r}><sup id={_footnote_id!r}>{_footnote_index}. {chunk.document.name}</sup></a>"
        )
        return citation

    # Replace all instances of (citation-<index>) with an html link on superscript "<index>"
    added_citations = re.sub(CITATION_PATTERN, replace_citation, response)

    # For now, don't show footnote list
    return added_citations  # + "</br>" + "</br>".join(footnote_list)


def replace_citation_ids(response: str, remapped_citations: dict[str, Subsection]) -> str:
    """Replace (citation-XX) in response with (citation-YY), where XX is the original citation ID
    and YY is the remapped citation ID"""

    def replace_citation(match: Match) -> str:
        citation_id = match.group(1)
        if citation_id not in remapped_citations:
            logger.error(
                "LLM generated a citation for a reference (%s) that doesn't exist.", citation_id
            )
            return ""
        return "(citation-" + remapped_citations[citation_id].id + ")"

    return re.sub(CITATION_PATTERN, replace_citation, response)

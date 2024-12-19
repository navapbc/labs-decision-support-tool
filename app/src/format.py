import logging
import random
import re
from collections import defaultdict
from itertools import groupby
from typing import Match, Sequence

import markdown

from src.citations import CITATION_PATTERN, remap_citation_ids
from src.db.models.document import Chunk, Document, Subsection

logger = logging.getLogger(__name__)

# We need a unique identifier for each accordion,
# even across multiple calls to this function.
# Choose a random number to avoid id collisions when hotloading the app during development.
_accordion_id = random.randint(0, 1000000)


class FormattingConfig:
    "Default formatting configuration"

    def __init__(self) -> None:
        self.add_citation_link_per_subsection = False

    def get_document_link(self, document: Document) -> str:
        if document.source:
            return f"<p>Source: <a href={document.source!r}>{document.source}</a></p>"
        return ""

    def get_citation_link(self, subsection: Subsection) -> str:
        return self.get_document_link(subsection.chunk.document)

    def get_superscript_link(self, chunk: Chunk) -> str:
        return chunk.document.source if chunk.document.source else "#"

    def format_accordion_body(self, citation_body: str) -> str:
        return to_html(citation_body)


def to_html(text: str) -> str:
    # markdown expects '\n' before the start of a list
    corrected_text = re.sub(r"^- ", "\n- ", text, flags=re.MULTILINE, count=1)
    return markdown.markdown(corrected_text)


def build_accordions(
    subsections: Sequence[Subsection], raw_response: str, config: FormattingConfig
) -> str:
    global _accordion_id

    remapped_citations = remap_citation_ids(subsections, raw_response)

    citations_html = ""
    map_of_accordion_ids = {}
    for document, cited_subsections in _group_by_document(remapped_citations).items():
        _accordion_id += 1
        citation_body = _build_citation_body(config, document, cited_subsections)
        formatted_citation_body = config.format_accordion_body(citation_body)
        citation_numbers = [citation.id for citation in cited_subsections]

        for citation_number in citation_numbers:
            map_of_accordion_ids[citation_number] = _accordion_id
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
    # as the next part of a list in response_with_citations
    response_with_citations = to_html(
        _add_citation_links(raw_response, remapped_citations, config, map_of_accordion_ids)
    )
    if citations_html:
        return (
            "<div>"
            + response_with_citations
            + "</div><h3>Source(s)</h3><div>"
            + citations_html
            + "</div>"
        )
    return "<div>" + response_with_citations + "</div>"


def _group_by_document(
    remapped_citations: dict[str, Subsection]
) -> dict[Document, list[Subsection]]:
    # Group the citations by document to build an accordion for each document
    citations_by_document: dict[Document, list[Subsection]] = defaultdict(list)
    # Combine all citations for each document
    for document, subsection_itr in groupby(
        remapped_citations.values(), key=lambda t: t.chunk.document
    ):
        citations_by_document[document] += list(subsection_itr)
    return citations_by_document


ChunkWithCitation = tuple[Chunk, Sequence[Subsection]]


def _build_citation_body(
    config: FormattingConfig, document: Document, subsections: Sequence[Subsection]
) -> str:
    citation_body = ""
    rendered_heading = ""
    for subsection in subsections:
        citation_headings = (
            _get_breadcrumb_html(subsection.text_headings, document.name)
            if subsection.text_headings
            else ""
        )
        # only show headings if they are different
        if rendered_heading != citation_headings:
            citation_body += f"<b>{citation_headings}</b>"
            rendered_heading = citation_headings

        citation_body += (
            f"<div>Citation #{subsection.id}: </div>"
            f'<div class="margin-left-2 border-left-1 border-base-lighter padding-left-2">{to_html(subsection.text)}</div>'
        )
        if config.add_citation_link_per_subsection:
            citation_link = config.get_citation_link(subsection)
            citation_body += f"<div>{citation_link}</div>"

    if not config.add_citation_link_per_subsection:
        citation_link = config.get_document_link(document)
        citation_body += f"<div>{citation_link}</div>"
    return citation_body


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


def reify_citations(
    response: str,
    subsections: Sequence[Subsection],
    config: FormattingConfig,
    map_of_accordion_ids: dict,
) -> str:
    remapped_citations = remap_citation_ids(subsections, response)
    return _add_citation_links(response, remapped_citations, config, map_of_accordion_ids)


_footnote_id = random.randint(0, 1000000)
_footnote_index = 0


# FIXME: Refactor to reduce code replication with replace_citation_ids()
def _add_citation_links(
    response: str,
    remapped_citations: dict[str, Subsection],
    config: FormattingConfig,
    map_of_accordion_ids: dict,
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

        matched_accordion_num = (
            map_of_accordion_ids[remapped_citations[citation_id].id]
            if map_of_accordion_ids and remapped_citations[citation_id].id in map_of_accordion_ids
            else None
        )

        citation = f"<sup><a class='accordion_item' data-id='a-{matched_accordion_num}' style='cursor:pointer'>{remapped_citations[citation_id].id}</a>&nbsp;</sup>"

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

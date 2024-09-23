import logging
import random
import re
from typing import Match, Sequence

from src.db.models.document import Chunk, ChunkWithScore, ChunkWithSubsection
from src.util.bem_util import get_bem_url

logger = logging.getLogger(__name__)

_footnote_id = random.randint(0, 1000000)
_footnote_index = 0

CITATION_PATTERN = r"\(citation-(\d+)\)"


def split_into_subsections(
    chunks: Sequence[Chunk], delimiter: str = "\n\n"
) -> Sequence[ChunkWithSubsection]:
    # Given a list of chunks, split them into a flat list of subsections
    context_mapping = []

    for chunk in chunks:
        for subsection in chunk.content.split(delimiter):
            context_mapping.append(ChunkWithSubsection(chunk, subsection))

    return context_mapping


def create_prompt_context(chunks: Sequence[Chunk]) -> str:
    context = split_into_subsections(chunks)

    context_list = []
    for index, chunk_with_subsection in enumerate(context):
        context_text = "Citation: citation-" + str(index) + "\n"
        context_text += "Document name: " + chunk_with_subsection.chunk.document.name + "\n"
        if chunk_with_subsection.chunk.headings:
            context_text += "Headings: " + " > ".join(chunk_with_subsection.chunk.headings) + "\n"
        context_text += "Content: " + chunk_with_subsection.subsection

        context_list.append(context_text)

    return "\n\n".join(context_list)


def dereference_citations(
    context: Sequence[ChunkWithSubsection], response: str
) -> dict[ChunkWithSubsection, int]:
    """
    Map (citation-<index>) in `response`, where index is the index in `context`,
    to a dict of ChunkWithSubsection, where the key of the dictionary is the ChunkWithSubsection
    that the citation refers to, and the value is the user-friendly citation number
    for that citation.
    E.g., if `context` is a list with five entries, and `response` is a string like
    "Example (citation-3)(citation-1), another example (citation-1).", then this function will return
    {context[3]: 1, context[1]: 2}; citations referencing context[3] should be shown to the user as "1" and
    citations referencing context[1] should be shown as "2".

    """
    citation_indices = re.findall(CITATION_PATTERN, response)

    # Maintain order and avoid duplicates by using a list and tracking seen indices
    citations: dict[ChunkWithSubsection, int] = {}
    citation_number = 1

    for index in citation_indices:

        index = int(index)  # Convert string to integer index
        # Check that index is in-bounds, since these are generated by the LLM,
        # so it's possible for it to hallucinate index numbers that don't exist
        if 0 <= index < len(context) and context[index] not in citations:
            citations[context[index]] = citation_number
            citation_number += 1

    return citations


def reify_citations(response: str, chunks: list[Chunk]) -> str:
    global _footnote_id
    _footnote_id += 1

    context = split_into_subsections(chunks)
    citation_to_numbers = dereference_citations(context, response)

    footnote_list = []

    # Replace (citation-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        index = int(match.group(1))
        global _footnote_index
        _footnote_index += 1
        # Leave a citation for chunks that don't exist alone
        if index >= len(context):
            logger.warning("LLM generated a citation for a reference ({index}) that doesn't exist.")
            return f"(citation-{index})"

        # Find the matching ChunkWithSubsection in the user-friendly
        # citation numbers and add 1 to get the citation number to display
        citation_number = citation_to_numbers[context[index]]

        chunk = context[index].chunk
        bem_link = get_bem_url(chunk.document.name) if "BEM" in chunk.document.name else "#"
        bem_link += "#page=" + str(chunk.page_number) if chunk.page_number else ""
        citation = f"<sup><a href={bem_link!r}>{citation_number}</a>&nbsp;</sup>"
        footnote_list.append(
            f"<a style='text-decoration:none' href={bem_link!r}><sup id={_footnote_id!r}>{_footnote_index}. {chunk.document.name}</sup></a>"
        )
        return citation

    # Replace all instances of (citation-<index>), where <index> is a number
    added_citations = re.sub(CITATION_PATTERN, replace_citation, response)

    # For now, don't show footnote list
    return added_citations  # + "</br>" + "</br>".join(footnote_list)


def reify_citations_with_scores(
    raw_response: str, chunks_with_scores: Sequence[ChunkWithScore]
) -> str:
    chunks = [c.chunk for c in chunks_with_scores]
    return reify_citations(raw_response, chunks)

import logging
import random
import re
from typing import Match, Sequence

from src.db.models.document import Chunk, ChunkWithSubsection
from src.util.bem_util import get_bem_url

logger = logging.getLogger(__name__)

_footnote_id = random.randint(0, 1000000)
_footnote_index = 0

CITATION_PATTERN = r"\(citation-(\d+)\)"


def _get_context(chunks: Sequence[Chunk]) -> Sequence[ChunkWithSubsection]:
    # Given a list of chunks, split them into a flat list of subsections
    context_mapping = []

    for chunk in chunks:
        for subsection in chunk.content.split("\n\n"):
            context_mapping.append(ChunkWithSubsection(chunk, subsection))

    return context_mapping


def get_context_for_prompt(chunks: Sequence[Chunk]) -> str:
    context = _get_context(chunks)

    context_list = []
    for index, chunk_with_subsection in enumerate(context):

        context_text = "Citation: citation-" + str(index) + "\n"
        context_text += "Document name: " + chunk_with_subsection.chunk.document.name + "\n"
        context_text += "Content: " + chunk_with_subsection.subsection

        context_list.append(context_text)

    return "\n\n".join(context_list)


def get_citation_numbers(
    context: Sequence[ChunkWithSubsection], response: str
) -> Sequence[ChunkWithSubsection]:
    """
    Map (citation-<index>) in `response`, where index is the index in `context`,
    to a user-friendly citation number.
    The user friendly citation number is the index of the entry in the returned list, plus one.
    E.g., if `context` is a list with five entries, and `response` is a string like
    "Example (citation-3)(citation-1), another example (citation-1).", then this function will return
    [context[3], [context[1]]; citations referencing context[3] should be shown to the user as "1" and
    citations referencing context[1] should be shown as "2".

    """
    citation_indices = re.findall(CITATION_PATTERN, response)

    # Maintain order and avoid duplicates by using a list and tracking seen indices
    seen = set()
    citations = []

    for index in citation_indices:
        idx = int(index)  # Convert string to integer index
        if 0 <= idx < len(context) and idx not in seen:
            citations.append(context[idx])
            seen.add(idx)

    return citations


def add_citations(response: str, chunks: list[Chunk]) -> str:
    global _footnote_id
    _footnote_id += 1

    context = _get_context(chunks)
    citation_numbers = get_citation_numbers(context, response)

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
        citation_number = 1 + citation_numbers.index(context[index])

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

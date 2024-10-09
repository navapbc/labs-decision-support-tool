import dataclasses
import logging
import random
import re
from itertools import count
from typing import Callable, Match, Sequence

from src.db.models.document import Chunk, ChunkWithScore, ChunkWithSubsection
from src.util.bem_util import get_bem_url

logger = logging.getLogger(__name__)

_footnote_id = random.randint(0, 1000000)
_footnote_index = 0

CITATION_PATTERN = r"\((citation-\d+)\)"


class CitationFactory:
    def __init__(self, start: int = 1, next_id: Callable | None = None):
        self.counter = count(start)
        if next_id:
            self.next_id = next_id
        else:
            self.next_id = lambda: f"citation-{self.counter.__next__()}"

    def create_citation(self, chunk: Chunk, subsection: str) -> ChunkWithSubsection:
        return ChunkWithSubsection(self.next_id(), chunk, subsection)


citation_factory = CitationFactory()


def split_into_subsections(
    chunks: Sequence[Chunk], delimiter: str = "\n\n", factory: CitationFactory | None = None
) -> Sequence[ChunkWithSubsection]:
    if factory is None:
        factory = citation_factory

    # Given a list of chunks, split them into a flat list of subsections
    context_mapping = []

    for chunk in chunks:
        for subsection in chunk.content.split(delimiter):
            context_mapping.append(factory.create_citation(chunk, subsection))

    return context_mapping


def create_prompt_context(subsections: Sequence[ChunkWithSubsection]) -> str:
    context_list = []
    for chunk_with_subsection in subsections:
        context_text = f"Citation: {chunk_with_subsection.id}\n"
        context_text += "Document name: " + chunk_with_subsection.chunk.document.name + "\n"
        if chunk_with_subsection.chunk.headings:
            context_text += "Headings: " + " > ".join(chunk_with_subsection.chunk.headings) + "\n"
        context_text += "Content: " + chunk_with_subsection.subsection

        context_list.append(context_text)

    return "\n\n".join(context_list)


# FIXME: rename to remap_citation_ids
def dereference_citations(
    subsections: Sequence[ChunkWithSubsection], response: str
) -> list[ChunkWithSubsection]:
    """
    Map (citation-<index>) in `response`, where index is the index in `subsections`,
    to a dict of ChunkWithSubsection, where the key of the dictionary is the ChunkWithSubsection
    that the citation refers to, and the value is the user-friendly citation number
    for that citation.
    E.g., if `subsections` is a list with five entries, and `response` is a string like
    "Example (citation-3)(citation-1), another example (citation-1).", then this function will return
    {subsections[3]: 1, subsections[1]: 2}; citations referencing subsections[3] should be shown to the user as "1" and
    citations referencing subsections[1] should be shown as "2".

    """
    # print()
    # for c in subsections:
    #     print(c.id, c.subsection)
    citation_map = {c.id: c for c in subsections}
    # print("dereference_citations", citation_map)

    citation_indices = re.findall(CITATION_PATTERN, response)

    # Maintain order and avoid duplicates by using a list and tracking seen indices
    seen_ids: set[str] = set()
    citations: list[ChunkWithSubsection] = []
    citation_number = count(start=1)

    for citation_id in citation_indices:
        # Check that index is in-bounds, since these are generated by the LLM,
        # so it's possible for it to hallucinate index numbers that don't exist
        if citation_id in citation_map and citation_id not in seen_ids:
            seen_ids.add(citation_id)
            citations.append(
                dataclasses.replace(citation_map[citation_id], id=str(citation_number.__next__()))
            )

    return citations


def reify_citations(response: str, subsections: Sequence[ChunkWithSubsection]) -> str:
    global _footnote_id
    _footnote_id += 1

    citation_to_numbers = dereference_citations(subsections, response)
    citation_map = {c.id: c for c in citation_to_numbers}
    print("citation_map", citation_map)

    footnote_list = []

    # Replace (citation-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        matched_text = match.group(1)
        global _footnote_index
        _footnote_index += 1
        # Leave a citation for chunks that don't exist alone
        citation_id = matched_text.removeprefix("citation-")
        logger.warning("citation_id: %s", citation_id)  # REMOVE
        if citation_id not in citation_map:
            logger.warning(
                "LLM generated a citation for a reference (%s) that doesn't exist.", citation_id
            )
            return f"({matched_text})"

        chunk = citation_map[citation_id].chunk
        bem_link = get_bem_url(chunk.document.name) if "BEM" in chunk.document.name else "#"
        bem_link += "#page=" + str(chunk.page_number) if chunk.page_number else ""
        citation = f"<sup><a href={bem_link!r}>{citation_id}</a>&nbsp;</sup>"
        footnote_list.append(
            f"<a style='text-decoration:none' href={bem_link!r}><sup id={_footnote_id!r}>{_footnote_index}. {chunk.document.name}</sup></a>"
        )
        return citation

    # Replace all instances of (citation-<index>), where <index> is a number
    added_citations = re.sub(CITATION_PATTERN, replace_citation, response)

    # For now, don't show footnote list
    return added_citations  # + "</br>" + "</br>".join(footnote_list)

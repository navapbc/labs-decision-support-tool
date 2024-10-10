import logging
import random
import re
from itertools import count
from typing import Callable, Match, Sequence

from src.db.models.document import Chunk, ChunkWithSubsection
from src.util.bem_util import get_bem_url

logger = logging.getLogger(__name__)

_footnote_id = random.randint(0, 1000000)
_footnote_index = 0

CITATION_PATTERN = r"\((citation-\d+)\)"


class CitationFactory:
    def __init__(self, start: int = 1, prefix: str = "citation-", next_id: Callable | None = None):
        self.counter = count(start)
        if next_id:
            self.next_id = next_id
        else:
            self.next_id = lambda: f"{prefix}{self.counter.__next__()}"

    def create_citation(self, chunk: Chunk, subsection: str) -> ChunkWithSubsection:
        return ChunkWithSubsection(self.next_id(), chunk, subsection)


citation_factory = CitationFactory()


def default_chunk_splitter(chunk: Chunk) -> list[str]:
    return chunk.content.split("\n\n")


def split_into_subsections(
    chunks: Sequence[Chunk],
    chunk_splitter: Callable = default_chunk_splitter,
    factory: CitationFactory = citation_factory,
) -> Sequence[ChunkWithSubsection]:
    # Given a list of chunks, split them into a flat list of subsections to be used as citations
    subsections = [
        factory.create_citation(chunk, subsection)
        for chunk in chunks
        for subsection in chunk_splitter(chunk)
    ]
    logger.info(
        "Split %d chunks into %d subsections:\n%s",
        len(chunks),
        len(subsections),
        "\n".join([f"{c.id}: {c.chunk.id}, {c.chunk.document.name}" for c in subsections]),
    )
    return subsections


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


def remap_citation_ids(
    subsections: Sequence[ChunkWithSubsection], response: str
) -> dict[str, ChunkWithSubsection]:
    """
    Map '(citation-<id>)' in `response`, where '(citation-<id>)' is the `id` in one of the `subsections`,
    to a dict from '(citation-<id>)' to corresponding ChunkWithSubsection,
    where the order of the list reflects the order of the citations in `response`.
    Remap the ChunkWithSubsection.id value to be the user-friendly citation number for that citation.
    E.g., if `subsections` is a list with five entries, and `response` is a string like
    "Example (citation-3)(citation-1), another example (citation-1).", then this function will return
    {"citation-3": ChunkWithSubsection(id="1",...), "citation-1": ChunkWithSubsection(id="2",...)} so that
    citations referencing '(citation-3)' can be shown to the user with id="1" and
    citations referencing '(citation-1)' can be shown with id="2".
    """
    citation_indices = re.findall(CITATION_PATTERN, response)

    # Avoid duplicates while maintaining citation order
    deduped_indices = []
    for x in citation_indices:
        if x not in deduped_indices:
            deduped_indices.append(x)

    # Create a lookup map from original citation id to the corresponding ChunkWithSubsection
    citation_map = {c.id: c for c in subsections}
    # Factory to create new consecutive citation ids
    factory = CitationFactory(start=1, prefix="")
    # Citations to be returned; note that uncited subsections are not included
    citations: dict[str, ChunkWithSubsection] = {}
    for citation_id in deduped_indices:
        # Since deduped_indices are generated by the LLM, it's possible for it to hallucinate a citation_id,
        # so check that each citation_id exists.
        if citation_id in citation_map:
            # Add a copy of the subsection with the id replaced by a new consecutive citation number
            citation = citation_map[citation_id]
            citations[citation_id] = factory.create_citation(citation.chunk, citation.subsection)
    logger.info(
        "Remapped citations:\n  %s",
        "\n  ".join([f"{id} -> {c.id}, {c.chunk.document.name}" for id, c in citations.items()]),
    )
    return citations


# TODO: move this to format.py
def reify_citations(response: str, subsections: Sequence[ChunkWithSubsection]) -> str:
    remapped_citations = remap_citation_ids(subsections, response)
    return add_citation_links(response, remapped_citations)


# TODO: move this to format.py since this is UI logic
def add_citation_links(response: str, remapped_citations: dict[str, ChunkWithSubsection]) -> str:
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

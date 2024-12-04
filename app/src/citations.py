import logging
import re
from dataclasses import dataclass
from itertools import count
from typing import Callable, Match, Sequence

from src.db.models.document import Chunk, Subsection

logger = logging.getLogger(__name__)

CITATION_PATTERN = r"\((citation-\d+)\)"


class CitationFactory:
    def __init__(self, start: int = 1, prefix: str = "citation-", next_id: Callable | None = None):
        self.counter = count(start)
        if next_id:
            self.next_id = next_id
        else:
            self.next_id = lambda: f"{prefix}{self.counter.__next__()}"

    def create_citation(self, chunk: Chunk, text: str, text_headings: Sequence[str]) -> Subsection:
        # Check that text is in chunk.content, ignoring whitespace
        assert re.sub(r"\s+", " ", text) in re.sub(
            r"\s+", " ", chunk.content
        ), f"Text {text!r} not found in chunk {chunk.content!r}"
        return Subsection(self.next_id(), chunk, text, text_headings)


citation_factory = CitationFactory()


def default_chunk_splitter(
    chunk: Chunk, factory: CitationFactory = citation_factory
) -> list[Subsection]:
    splits = [split for split in chunk.content.split("\n\n") if split]
    # Rejoin headings with the subsequent first paragraph
    better_splits = []
    skip_next = False
    curr_headings = chunk.headings or []
    # FIXME: update curr_headings as we go through the splits
    for i, split in enumerate(splits):
        if skip_next:
            skip_next = False
            continue

        next_split = splits[i + 1] if i + 1 < len(splits) else None
        if next_split and split.startswith("#") and not next_split.startswith("#"):
            subsection = factory.create_citation(chunk, f"{split}\n{next_split}", curr_headings)
            better_splits.append(subsection)
            skip_next = True
            continue

        better_splits.append(factory.create_citation(chunk, split, curr_headings))

    return better_splits


def split_into_subsections(
    chunks: Sequence[Chunk],
    chunk_splitter: Callable = default_chunk_splitter,
    factory: CitationFactory = citation_factory,
) -> Sequence[Subsection]:
    # Given a list of chunks, split them into a flat list of subsections to be used as citations
    subsections = [subsection for chunk in chunks for subsection in chunk_splitter(chunk, factory)]
    logger.info(
        "Split %d chunks into %d subsections:\n%s",
        len(chunks),
        len(subsections),
        "\n".join([f"{c.id}: {c.chunk.id}, {c.chunk.document.name}" for c in subsections]),
    )
    return subsections


def create_prompt_context(subsections: Sequence[Subsection]) -> str:
    context_list = []
    for subsection in subsections:
        context_text = f"Citation: {subsection.id}\n"
        context_text += "Document name: " + subsection.chunk.document.name + "\n"
        if subsection.text_headings:
            context_text += "Headings: " + " > ".join(subsection.text_headings) + "\n"
        context_text += "Content: " + subsection.text

        context_list.append(context_text)

    return "\n\n".join(context_list)


def remap_citation_ids(subsections: Sequence[Subsection], response: str) -> dict[str, Subsection]:
    """
    Map '(citation-<id>)' in `response`, where '(citation-<id>)' is the `id` in one of the `subsections`,
    to a dict from '(citation-<id>)' to corresponding Subsection,
    where the order of the list reflects the order of the citations in `response`.
    Only cited subsections are included in the returned dict.
    Remap the Subsection.id value to be the user-friendly citation number for that citation.
    E.g., if `subsections` is a list with five entries, and `response` is a string like
    "Example (citation-3)(citation-1), another example (citation-1).", then this function will return
    {"citation-3": Subsection(id="1",...), "citation-1": Subsection(id="2",...)} so that
    citations referencing '(citation-3)' can be shown to the user with id="1" and
    citations referencing '(citation-1)' can be shown with id="2".
    """
    citation_indices = re.findall(CITATION_PATTERN, response)

    # Avoid duplicates while maintaining citation order
    deduped_indices = []
    for x in citation_indices:
        if x not in deduped_indices:
            deduped_indices.append(x)

    # Create a lookup map from original citation id to the corresponding Subsection
    citation_map = {c.id: c for c in subsections}
    # Factory to create new consecutive citation ids
    factory = CitationFactory(start=1, prefix="")
    # Citations to be returned; note that uncited subsections are not included
    citations: dict[str, Subsection] = {}
    for citation_id in deduped_indices:
        # Since deduped_indices are generated by the LLM, it's possible for it to hallucinate a citation_id,
        # so check that each citation_id exists.
        if citation_id in citation_map:
            # Add a copy of the subsection with the id replaced by a new consecutive citation number
            citation = citation_map[citation_id]
            citations[citation_id] = factory.create_citation(
                citation.chunk, citation.text, citation.text_headings
            )
    logger.info(
        "Remapped citations:\n  %s",
        "\n  ".join([f"{id} -> {c.id}, {c.chunk.document.name}" for id, c in citations.items()]),
    )
    return citations


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


@dataclass
class ResponseWithSubsections:
    response: str
    subsections: Sequence[Subsection]


def simplify_citation_numbers(result: ResponseWithSubsections) -> ResponseWithSubsections:
    """
    Returns the response with remapped `(citation-X)` strings and
    a list of subsections representing the citations.
    The returned subsections only contain citations used in the response
    and are ordered consecutively starting from 1.
    """
    remapped_citations = remap_citation_ids(result.subsections, result.response)
    remapped_response = replace_citation_ids(result.response, remapped_citations)
    return ResponseWithSubsections(remapped_response, tuple(remapped_citations.values()))

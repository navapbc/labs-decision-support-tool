import logging
import re
from itertools import count
from typing import Callable, Match, NamedTuple, Optional, Sequence, Tuple

from nutree import Node

from src.db.models.document import Chunk, Subsection
from src.ingestion.markdown_tree import create_markdown_tree, get_parent_headings_raw
from src.util.string_utils import parse_heading_markdown

logger = logging.getLogger(__name__)

CITATION_PATTERN = r"\((citation-\d+)\)"


class CitationFactory:
    def __init__(self, start: int = 1, prefix: str = "citation-", next_id: Callable | None = None):
        self.counter = count(start)
        if next_id:
            self.next_id = next_id
        else:
            self.next_id = lambda: f"{prefix}{next(self.counter)}"

    def create_citation(
        self,
        chunk: Chunk,
        subsection_index: int,
        text: str,
        text_headings: Optional[Sequence[str]] = None,
    ) -> Subsection:
        if not self._text_in_chunk(text, chunk):
            logger.warning("Text not found in chunk: %r\n%r", text, chunk.content)
        return Subsection(self.next_id(), chunk, subsection_index, text, text_headings)

    def _text_in_chunk(self, text: str, chunk: Chunk) -> bool:
        # Check that text is in chunk.content, ignoring whitespace and dashes
        stripped_text = re.sub(r"\s+|-", "", text)
        stripped_chunk_text = re.sub(r"\s+|-", "", chunk.content)
        return stripped_text in stripped_chunk_text


citation_factory = CitationFactory()


def default_chunk_splitter(
    chunk: Chunk, factory: CitationFactory = citation_factory
) -> list[Subsection]:
    try:
        return tree_based_chunk_splitter(chunk, factory)
    except RuntimeError as e:
        logger.warning(
            "Falling back to basic_chunk_splitter for chunk: %s", chunk.id, exc_info=True
        )
        logger.warning(e)
        return basic_chunk_splitter(chunk, factory)


def basic_chunk_splitter(
    chunk: Chunk, factory: CitationFactory = citation_factory
) -> list[Subsection]:
    splits = [split for split in chunk.content.split("\n\n") if split]
    better_splits = []
    base_headings = chunk.headings or []
    curr_headings = ["" for _ in range(6)]
    split_index = count()
    for split in splits:
        if split.startswith("#"):
            heading_level, heading_text = parse_heading_markdown(split)
            curr_headings[heading_level] = heading_text
            # Clear all headings after the heading_level
            for i in range(heading_level + 1, len(curr_headings)):
                curr_headings[i] = ""
            continue

        headings = [text for text in base_headings + curr_headings if text]
        better_splits.append(factory.create_citation(chunk, next(split_index), split, headings))
    return better_splits


def tree_based_chunk_splitter(
    chunk: Chunk, factory: CitationFactory = citation_factory
) -> list[Subsection]:
    tree = create_markdown_tree(chunk.content)
    subsections: list[Subsection] = []
    _split_section(subsections, tree.first_child(), chunk, factory)
    return subsections


def _split_section(
    subsections: list[Subsection],
    hs_node: Node,
    chunk: Chunk,
    factory: CitationFactory = citation_factory,
) -> None:
    base_headings = chunk.headings or []
    headings = None
    node = hs_node.first_child()
    while node:
        if node.data_type == "HeadingSection":
            _split_section(subsections, node, chunk, factory)
        elif node.data_type == "Heading":
            pass
        elif node.has_token() and node.is_block_token():
            headings = headings or (base_headings + get_parent_headings_raw(node))
            markdown = node.render().strip()

            if (
                node.data_type == "Paragraph"
                and (next_node := node.next_sibling())
                and next_node.data_type == "List"
            ):
                intro_sentence = markdown
                markdown = next_node.render().strip()
                subsections.append(
                    factory.create_citation(
                        chunk, len(subsections), intro_sentence + "\n" + markdown, headings
                    )
                )
                node.next_sibling().remove()
            else:
                subsections.append(
                    factory.create_citation(chunk, len(subsections), markdown, headings)
                )
        else:
            raise NotImplementedError(f"Unexpected: {node.id_string()}")
        node = node.next_sibling()


def split_into_subsections(
    chunks: Sequence[Chunk],
    chunk_splitter: Callable = default_chunk_splitter,
    factory: CitationFactory = citation_factory,
) -> Sequence[Subsection]:
    # Given a list of chunks, split them into a flat list of subsections to be used as citations
    subsections = [subsection for chunk in chunks for subsection in chunk_splitter(chunk, factory)]
    logger.info(
        "Split %d chunks into %d subsections",
        len(chunks),
        len(subsections),
        # "\n".join([f"{c.id}: {c.chunk.id}, {c.chunk.document.name}" for c in subsections]),
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
    Map '(citation-<id>)' in `response`, where '(citation-<id>)' refers to the `id` in one of the `subsections`,
    to a dict from string '(citation-<id>)' to the corresponding Subsection,
    where the order of the list reflects the order of the citations in `response`.
    Only cited subsections in the response are included in the returned dict.
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
                citation.chunk, citation.subsection_index, citation.text, citation.text_headings
            )
    if citations:
        logger.info(
            "Remapped citations:\n  %s",
            "\n  ".join(
                [f"{id} -> {c.id}, {c.chunk.document.name}" for id, c in citations.items()]
            ),
        )
    return citations


def remove_unknown_citation_ids(response: str, subsections: Sequence[Subsection]) -> str:
    subsection_dict: dict[str, Subsection] = {ss.id: ss for ss in subsections}

    def replace_unknown_id(match: Match) -> str:
        citation_id = match.group(1)
        if citation_id not in subsection_dict:
            logger.warning("Removing unknown %r", citation_id)
            return ""
        return f"({citation_id})"

    return re.sub(CITATION_PATTERN, replace_unknown_id, response)


def replace_citation_ids(response: str, remapped_citations: dict[str, Subsection]) -> str:
    """Replace (citation-XX) in response with (citation-YY), where XX is the original citation ID
    and YY is the remapped citation ID"""

    def replace_with_new_id(match: Match) -> str:
        citation_id = match.group(1)
        return "(citation-" + remapped_citations[citation_id].id + ")"

    return re.sub(CITATION_PATTERN, replace_with_new_id, response)


def merge_contiguous_cited_subsections(
    response: str, subsections: Sequence[Subsection]
) -> Tuple[str, Sequence[Subsection]]:
    subsection_dict: dict[str, Subsection] = {ss.id: ss for ss in subsections}
    updated_subsections = {ss.id: ss for ss in subsections}
    # logger.info(
    #     "Merging any contiguous citations:\n  %s",
    #     "\n  ".join([f"{ss.id} -> {ss.chunk.id}, {ss.subsection_index}" for ss in subsections]),
    # )

    def group_contiguous_cited_subsections(
        multiple_citations_group: str,
    ) -> Sequence[Sequence[Subsection]]:
        citations = re.findall(CITATION_PATTERN, multiple_citations_group)
        # Initialize looping variables based on the first citation
        ss = subsection_dict[citations[0]]
        curr_group = [ss]
        contig_groups = [curr_group]
        for citation_id in citations[1:]:
            curr_ss = subsection_dict[citation_id]
            if curr_ss.chunk == ss.chunk and curr_ss.subsection_index == ss.subsection_index + 1:
                # This subsection is contiguous with the previous one
                curr_group.append(curr_ss)
            else:
                # Create a new contiguous group
                curr_group = [curr_ss]
                contig_groups.append(curr_group)

            # Update looping variable
            ss = curr_ss
        return contig_groups

    def merge_citations(match: Match) -> str:
        multiple_citations_group = match.group(1)
        contig_groups = group_contiguous_cited_subsections(multiple_citations_group)

        new_citation_strs = []
        for contig_group in contig_groups:
            if len(contig_group) == 1:
                # Use the single citation as is
                citation_id = contig_group[0].id
                new_ss = subsection_dict[citation_id]
            else:
                # Merge the citations into a string of numbers so that it still matches CITATION_PATTERN
                # concat_ids should be deterministic and unique to match the same repeated citations
                concat_ids = "".join(
                    [ss.id.removeprefix("citation-").zfill(4) for ss in contig_group]
                )
                citation_id = f"citation-{concat_ids}"
                if citation_id in updated_subsections:
                    new_ss = updated_subsections[citation_id]
                else:
                    logger.info("Merging %d citations into %s", len(contig_group), citation_id)
                    new_ss = Subsection(
                        id=citation_id,
                        chunk=contig_group[0].chunk,
                        subsection_index=contig_group[0].subsection_index,
                        text="\n\n".join([ss.text for ss in contig_group]),
                        text_headings=contig_group[0].text_headings,
                    )

            updated_subsections[new_ss.id] = new_ss
            new_citation_strs.append(f" ({citation_id})")
        return "".join(new_citation_strs)

    # Find multiple citations that are listed together
    new_response = re.sub(r"(( ?\(citation-\d+\)){2,})", merge_citations, response)
    return (new_response, tuple(updated_subsections.values()))


def move_citations_after_punctuation(response: str) -> str:
    def move_citation(match: Match) -> str:
        citations = match.group(1)
        # match.group(2) only has the last citation in match.group(1)
        # see https://stackoverflow.com/a/43866169/23458508
        punctuation = match.group(3)
        return f"{punctuation} {citations}"

    # Include any left-side spaces so the replacement punctuation immediately follows the last word
    return re.sub(r" *(( *\(citation-\d+\))+) *([\.\?\!])", move_citation, response).strip()


class ResponseWithSubsections(NamedTuple):
    response: str
    subsections: Sequence[Subsection]


def simplify_citation_numbers(
    response: str, subsections: Sequence[Subsection]
) -> ResponseWithSubsections:
    """
    Returns the response with remapped `(citation-X)` strings and
    a list of subsections representing the citations.
    The returned subsections only contain citations used in the response
    and are ordered consecutively starting from 1.
    """
    cleaned_response = remove_unknown_citation_ids(response, subsections)
    formatted_response = move_citations_after_punctuation(cleaned_response)

    merged_subsection_response, merged_subsections = merge_contiguous_cited_subsections(
        formatted_response, subsections
    )

    remapped_citations = remap_citation_ids(merged_subsections, merged_subsection_response)
    remapped_response = replace_citation_ids(merged_subsection_response, remapped_citations)

    return ResponseWithSubsections(remapped_response, tuple(remapped_citations.values()))

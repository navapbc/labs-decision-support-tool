import logging
import random
import re
from typing import Match, Sequence

from src.db.models.document import Chunk, ChunkWithScore
from src.format import _get_bem_url

logger = logging.getLogger(__name__)

_footnote_id = random.randint(0, 1000000)
_footnote_index = 0


def get_context_for_prompt(chunks: Sequence[ChunkWithScore]) -> str:
    return "\n\n".join(
        [
            f"Citation: chunk-{index}\nDocument name: {chunk.chunk.document.name}\nContent: {chunk.chunk.content}"
            for index, chunk in enumerate(chunks)
        ]
    )


def add_citations(response: str, chunks: list[Chunk]) -> str:
    global _footnote_id

    _footnote_id += 1

    footnote_list = []

    # Replace (chunk-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        index = int(match.group(1))
        global _footnote_index
        _footnote_index += 1
        # Leave a citation for chunks that don't exist alone
        if index >= len(chunks):
            logger.warning("LLM generated a citation for a chunk ({index}) that doesn't exist.")
            return f"(chunk-{index})"

        chunk = chunks[index]
        bem_link = _get_bem_url(chunk.document.name) if "BEM" in chunk.document.name else "#"
        citation = f".<sup><a href={bem_link!r} id={_footnote_id!r}>{_footnote_index}</a></sup>"
        footnote_list.append(
            f"<a style='text-decoration:none' href={bem_link!r}><sup id={_footnote_id!r}>{_footnote_index}. {chunk.document.name}</sup></a>"
        )
        return citation

    # Replace all instances of (chunk-<index>), where <index> is a number
    added_citations = re.sub(r"\(chunk-(\d+)\).", replace_citation, response)
    return added_citations + "</br>" + "</br>".join(footnote_list)

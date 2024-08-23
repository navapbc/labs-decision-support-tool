import logging
import re
from typing import Match

from src.db.models.document import Chunk

logger = logging.getLogger(__name__)


def add_citations(response: str, chunks: list[Chunk]) -> str:
    # Replace (chunk-<index>) with the appropriate citation
    def replace_citation(match: Match) -> str:
        index = int(match.group(1))
        # Leave a citation for chunks that don't exist alone
        if index >= len(chunks):
            logger.warning("LLM generated a citation for a chunk ({index}) that doesn't exist.")
            return f"(chunk-{index})"

        chunk = chunks[index]

        return f"([{chunk.document.name}]({chunk.document}))"

    # Replace all instances of (chunk-<index>), where <index> is a number
    return re.sub(r"\(chunk-(\d+)\)", replace_citation, response)

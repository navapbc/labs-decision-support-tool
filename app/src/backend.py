import logging
from typing import Any, Sequence

from asyncer import asyncify

from src.chat_engine import ChatEngineInterface, OnMessageResult
from src.db.models.document import ChunkWithScore

logger = logging.getLogger(__name__)


async def run_engine(engine: ChatEngineInterface, question: str) -> tuple[OnMessageResult, Any]:
    logger.info("Received: %s", question)

    result = await asyncify(lambda: engine.on_message(question=question))()

    formatted_answer = engine.formatter(
        chunks_shown_max_num=engine.chunks_shown_max_num,
        chunks_shown_min_score=engine.chunks_shown_min_score,
        chunks_with_scores=result.chunks_with_scores,
        raw_response=result.response,
    )

    return (result, formatted_answer)


def get_retrieval_metadata(chunks_with_scores: Sequence[ChunkWithScore]) -> dict:
    return {
        "chunks": [
            {
                "document.name": chunk_with_score.chunk.document.name,
                "chunk.id": str(chunk_with_score.chunk.id),
                "score": chunk_with_score.score,
            }
            for chunk_with_score in chunks_with_scores
        ]
    }

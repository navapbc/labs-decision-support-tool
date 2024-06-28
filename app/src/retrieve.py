from typing import Sequence, Tuple

from sentence_transformers import SentenceTransformer
from sqlalchemy import Row, select

import src.adapters.db as db
from src.db.models.document import Chunk


def retrieve(
    db_session: db.Session, embedding_model: SentenceTransformer, query: str, k: int = 5
) -> Sequence[Row[Tuple[Chunk, float]]]:
    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    return db_session.execute(
        select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .limit(k)
    ).all()

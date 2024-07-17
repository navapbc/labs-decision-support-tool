import logging
from pprint import pprint
from typing import Sequence, Tuple

from sentence_transformers import SentenceTransformer
from sqlalchemy import Row, select

import src.adapters.db as db
from src.db.models.document import Chunk, Document

logger = logging.getLogger(__name__)
_DEBUGGING = True
if _DEBUGGING:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


def retrieve(
    db_session: db.Session,
    embedding_model: SentenceTransformer,
    query: str,
    k: int = 5,
    benefit_programs: Sequence | None = None,
) -> Sequence[Chunk]:
    logger.info(f"Retrieving context for {query!r}")

    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    if _DEBUGGING:
        docstmt = select(Document.name, Document.program, Document.region)
        print("stmt", docstmt.compile(compile_kwargs={"literal_binds": True}))
        docs = db_session.execute(docstmt).all()
        print("docs:", docs)

        chstmt = select(Chunk.tokens, Document.program, Chunk.content).join(Chunk.document)
        chs = db_session.execute(chstmt).all()
        print("chunks:")
        pprint(chs)
        if benefit_programs:
            chs = db_session.execute(chstmt.filter(Document.program.in_(benefit_programs))).all()
            print("filtered chunks:")
            pprint(chs)

    statement = select(Chunk).join(Chunk.document)
    if benefit_programs:
        statement = statement.filter(Document.program.in_(benefit_programs))
    rchs = db_session.execute(statement.limit(k)).all()

    if _DEBUGGING:
        print("returned chunks:")
        pprint(rchs)

    chunks = db_session.scalars(
        statement.order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding)).limit(k)
    ).all()

    for chunk in chunks:
        print(f"Retrieved: {chunk.document.name!r} {chunk.content!r}")

    return chunks


def retrieve_with_scores(
    db_session: db.Session, embedding_model: SentenceTransformer, query: str, k: int = 5
) -> Sequence[Row[Tuple[Chunk, float]]]:
    logger.info(f"Retrieving context for {query!r}")

    query_embedding = embedding_model.encode(query, show_progress_bar=False)

    chunks_with_scores = db_session.execute(
        select(Chunk, Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .order_by(Chunk.mpnet_embedding.max_inner_product(query_embedding))
        .limit(k)
    ).all()

    for chunk, score in chunks_with_scores:
        logger.info(f"Retrieved: {chunk.document.name!r} with score {score}")

    return chunks_with_scores

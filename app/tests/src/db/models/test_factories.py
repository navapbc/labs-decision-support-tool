from sqlalchemy import delete, select

import src.adapters.db as db
from src.db.models.document import Chunk, Document
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


def test_document_factory(enable_factory_create, db_session: db.Session):
    # Delete Documents created by other tests
    db_session.execute(delete(Document))

    document = DocumentFactory.create()

    db_record = db_session.execute(select(Document)).scalar_one()
    assert db_record.id == document.id
    assert db_record.content == document.content
    assert db_record.name == document.name


def test_chunk_factory(enable_factory_create, db_session: db.Session):
    # Delete Documents and Chunks (by cascade) created by other tests
    db_session.execute(delete(Document))

    chunk = ChunkFactory.create()

    document_db_record = db_session.execute(select(Document)).scalar_one()
    assert document_db_record.id == chunk.document_id

    chunk_db_record = db_session.execute(select(Chunk)).scalar_one()
    assert chunk_db_record.id == chunk.id
    assert chunk_db_record.content == chunk.content
    assert chunk_db_record.tokens == MockSentenceTransformer.tokenizer.tokenize(chunk.content)
    assert chunk_db_record.embedding == MockSentenceTransformer().encode(chunk.content)

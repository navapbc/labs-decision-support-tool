import logging
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, IdMixin, TimestampMixin

logger = logging.getLogger(__name__)


class Document(Base, IdMixin, TimestampMixin):
    __tablename__ = "document"

    name: Mapped[str]
    content: Mapped[str | None]

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete"
    )

    # Domain-specific columns follow
    # dataset in which the document belongs
    dataset: Mapped[str]
    # benefit program
    program: Mapped[str]
    # geographical region of the benefit program
    region: Mapped[str]


class Chunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "chunk"

    content: Mapped[str]
    tokens: Mapped[int | None]
    mpnet_embedding: Mapped[np.ndarray] = mapped_column(Vector(768))

    document_id: Mapped[UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    document: Mapped[Document] = relationship(Document)

    page_number: Mapped[int]
    # Flattened 'headings' data from grouped_texts
    headings: Mapped[list[str]]
    # Number of splits (or chunks) the text was split into, = 1 (if not split)
    num_splits: Mapped[int] = 1
    # If not complete (num_splits > 1), specify the index starting from 0
    split_index: Mapped[int] = 0


@dataclass
class ChunkWithScore:
    chunk: Chunk
    score: float


@dataclass
class DocumentWithMaxScore:
    document: Document
    # The maxmium similarity score of all Chunks associated with that document
    max_score: float

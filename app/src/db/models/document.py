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


@dataclass
class ChunkWithScore:
    chunk: Chunk
    score: float

import logging
from typing import NamedTuple, Optional, Sequence
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
    content: Mapped[str | None] = mapped_column(comment="Content of the document")

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete"
    )

    source: Mapped[str | None] = mapped_column(comment="Source of the document, e.g., a URI")

    # Domain-specific columns follow
    dataset: Mapped[str] = mapped_column(comment="dataset in which the document belongs")
    program: Mapped[str] = mapped_column(comment="benefit program")
    region: Mapped[str] = mapped_column(comment="geographical region of the benefit program")


class Chunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "chunk"

    content: Mapped[str] = mapped_column(comment="Content of the chunk")
    tokens: Mapped[int | None] = mapped_column(comment="Number of tokens in the content")
    mpnet_embedding: Mapped[np.ndarray] = mapped_column(
        Vector(768), comment="MPNet embedding of the content"
    )

    document_id: Mapped[UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    document: Mapped[Document] = relationship(Document)

    page_number: Mapped[int | None] = mapped_column(
        comment="Page number of the chunk in the original document"
    )
    headings: Mapped[list[str] | None] = mapped_column(
        comment="List of 'headings' from grouped_texts"
    )
    num_splits: Mapped[int] = mapped_column(
        default=1, comment="Number of chunks the original text was split into"
    )
    split_index: Mapped[int] = mapped_column(
        default=0, comment="Index of this chunk within splits (0-based)"
    )

    def to_json(self) -> dict[str, str | int | list[str]]:
        as_json: dict[str, str | int | list[str]] = {
            "id": str(self.id),
            "content": self.content,
            "document_id": str(self.document_id),
            "headings": self.headings if self.headings else [],
            "num_splits": self.num_splits,
            "split_index": self.split_index,
        }
        if self.page_number:
            as_json["page_number"] = self.page_number
        return as_json


class ChunkWithScore(NamedTuple):
    chunk: Chunk
    score: float


class DocumentWithMaxScore(NamedTuple):
    document: Document
    # The maximium similarity score of all Chunks associated with that document
    max_score: float


class Subsection:

    def __init__(
        self,
        id: str,
        chunk: Chunk,
        subsection_index: int,
        text: str,
        text_headings: Optional[Sequence[str]] = None,
    ) -> None:
        # user-friendly, consecutive identifier for the subsection starting from 1
        self.id = id
        # chunk containing the subsection
        self.chunk = chunk
        # index of the subsection within the chunk (0-based)
        self.subsection_index = subsection_index
        # specific substring within chunk.text
        self.text = text
        # parent headings for the text
        self.text_headings = text_headings or chunk.headings or []
        # text_headings should start with the chunk headings
        assert all(
            self.text_headings[i] == heading for i, heading in enumerate(chunk.headings or [])
        ), f"Text headings {self.text_headings!r} do not start with chunk headings {chunk.headings!r}"

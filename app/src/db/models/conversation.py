import logging
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, IdMixin, TimestampMixin

logger = logging.getLogger(__name__)


class ChatMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_message"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("user_session.session_id"),
        comment="Session ID that this message is associated with",
    )
    role: Mapped[str] = mapped_column(comment="Role of the message speaker")
    content: Mapped[str] = mapped_column(comment="Content of the message")
    session: Mapped["UserSession"] = relationship("UserSession", back_populates="chat_messages")


class UserSession(Base, TimestampMixin):
    __tablename__ = "user_session"

    session_id: Mapped[str] = mapped_column(primary_key=True, comment="Session ID")
    user_id: Mapped[str] = mapped_column(
        comment="External user ID that this session was created for"
    )
    chat_engine_id: Mapped[str] = mapped_column(comment="Chat engine ID for this session")
    lai_thread_id: Mapped[str | None] = mapped_column(
        comment="LiteralAI's thread ID corresponding to session_id"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        order_by="ChatMessage.created_at",
    )


# -------------------------------
# The following is based on the expected schema at https://github.com/Chainlit/chainlit-datalayer/tree/main/prisma/migrations
# It creates tables expected for Chainlit's Official Data Layer -- https://docs.chainlit.io/data-layers/official
# (which is slightly different from the SQLAlchemy Data Layer -- https://docs.chainlit.io/data-layers/sqlalchemy)
# The table and column names must be what Chainlit expects.
# The expected `metadata` column conflicts with Base(DeclarativeBase)'s metadata field, so use `metadata_col` attribute name instead.
# -------------------------------

class StepType(str, Enum):
    ASSISTANT_MESSAGE = "assistant_message"
    EMBEDDING = "embedding"
    LLM = "llm"
    RETRIEVAL = "retrieval"
    RERANK = "rerank"
    RUN = "run"
    SYSTEM_MESSAGE = "system_message"
    TOOL = "tool"
    UNDEFINED = "undefined"
    USER_MESSAGE = "user_message"


class Element(Base, IdMixin, TimestampMixin):
    __tablename__ = "Element"

    thread_id: Mapped[UUID | None] = mapped_column(ForeignKey("Thread.id", ondelete="CASCADE"))
    step_id: Mapped[UUID] = mapped_column(ForeignKey("Step.id", ondelete="CASCADE"))
    metadata_col = Column(JSON, name="metadata", nullable=False)
    mime: Mapped[str | None]
    name: Mapped[str]
    object_key: Mapped[str | None]
    url: Mapped[str | None]
    chainlit_key: Mapped[str | None]
    display: Mapped[str | None]
    size: Mapped[str | None]
    language: Mapped[str | None]
    page: Mapped[int | None]
    props = Column(JSON)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "User"

    metadata_col = Column(JSON, name="metadata", nullable=False)
    identifier: Mapped[str] = mapped_column(unique=True)


class Feedback(Base, IdMixin, TimestampMixin):
    __tablename__ = "Feedback"

    step_id: Mapped[UUID | None] = mapped_column(ForeignKey("Step.id", ondelete="SET NULL"))
    name: Mapped[str]
    value: Mapped[int]
    comment: Mapped[str | None]


class Step(Base, IdMixin, TimestampMixin):
    __tablename__ = "Step"

    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("Step.id", ondelete="CASCADE"))
    thread_id: Mapped[UUID | None] = mapped_column(ForeignKey("Thread.id", ondelete="CASCADE"))

    input: Mapped[str | None]
    metadata_col = Column(JSON, name="metadata", nullable=False)
    name: Mapped[str | None]
    output: Mapped[str | None]
    type: Mapped[StepType]  # = Column(SQLEnum(StepType), nullable=False)
    show_input: Mapped[str] = mapped_column(default="json")
    is_error: Mapped[bool] = mapped_column(default=False)
    start_time: Mapped[datetime]
    end_time: Mapped[datetime]


class Thread(Base, IdMixin, TimestampMixin):
    __tablename__ = "Thread"

    deleted_at: Mapped[datetime | None]
    name: Mapped[str | None]
    metadata_col = Column(JSON, name="metadata", nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("User.id", ondelete="SET NULL"))
    tags: Mapped[list[str]] = mapped_column(default=[])

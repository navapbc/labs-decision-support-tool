import logging
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import ARRAY, Boolean, Column, ForeignKey, Text, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
# Also column names are expected to be camelcase (e.g., stepId, threadId, createdAt, startTime).
# -------------------------------


class StepType(str, Enum):
    assistant_message = "assistant_message"
    embedding = "embedding"
    llm = "llm"
    retrieval = "retrieval"
    rerank = "rerank"
    run = "run"
    system_message = "system_message"
    tool = "tool"
    undefined = "undefined"
    user_message = "user_message"


class Element(Base, IdMixin):
    __tablename__ = "Element"

    created_at: Mapped[datetime] = mapped_column(name="createdAt", server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(name="updatedAt", server_default=sa.text("now()"))

    thread_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("Thread.id", ondelete="CASCADE"), name="threadId"
    )
    step_id: Mapped[UUID] = mapped_column(ForeignKey("Step.id", ondelete="CASCADE"), name="stepId")
    metadata_col = Column(JSONB, name="metadata", nullable=False)
    mime: Mapped[str | None]
    name: Mapped[str]
    object_key: Mapped[str | None] = mapped_column(name="objectKey")
    url: Mapped[str | None]
    chainlit_key: Mapped[str | None] = mapped_column(name="chainlitKey")
    display: Mapped[str | None]
    size: Mapped[str | None]
    language: Mapped[str | None]
    page: Mapped[int | None]
    props = Column(JSONB)


class User(Base, IdMixin):
    __tablename__ = "User"

    created_at: Mapped[datetime] = mapped_column(name="createdAt", server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(name="updatedAt", server_default=sa.text("now()"))

    metadata_col = Column(JSONB, name="metadata", nullable=False)
    identifier: Mapped[str] = mapped_column(unique=True)


class Feedback(Base, IdMixin):
    __tablename__ = "Feedback"

    created_at: Mapped[datetime] = mapped_column(name="createdAt", server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(name="updatedAt", server_default=sa.text("now()"))

    step_id: Mapped[UUID | None] = mapped_column(ForeignKey("Step.id", ondelete="SET NULL"), name="stepId")
    name: Mapped[str]
    value: Mapped[int]
    comment: Mapped[str | None]


class Step(Base, IdMixin):
    __tablename__ = "Step"

    created_at: Mapped[datetime] = mapped_column(name="createdAt", server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(name="updatedAt", server_default=sa.text("now()"))

    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("Step.id", ondelete="CASCADE"), name="parentId"
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("Thread.id", ondelete="CASCADE"), name="threadId"
    )

    input: Mapped[str | None]
    metadata_col = Column(JSONB, name="metadata", nullable=False)
    name: Mapped[str | None]
    output: Mapped[str | None]
    type: Mapped[StepType]  # = Column(SQLEnum(StepType), nullable=False)
    show_input: Mapped[str] = mapped_column(server_default="json", name="showInput")
    is_error: Mapped[bool] = mapped_column(Boolean, server_default=sql.false(), name="isError")
    start_time: Mapped[datetime] = mapped_column(name="startTime")
    end_time: Mapped[datetime] = mapped_column(name="endTime")


class Thread(Base, IdMixin):
    __tablename__ = "Thread"

    created_at: Mapped[datetime] = mapped_column(name="createdAt", server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(name="updatedAt", server_default=sa.text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(name="deletedAt")
    name: Mapped[str | None]
    metadata_col = Column(JSONB, name="metadata", nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("User.id", ondelete="SET NULL"), name="userId"
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")

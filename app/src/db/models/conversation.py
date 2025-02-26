import logging

from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base, IdMixin, TimestampMixin

logger = logging.getLogger(__name__)


class ChatMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_message"

    session_id: Mapped[str] = mapped_column(
        comment="Session ID that this message is associated with"
    )
    role: Mapped[str] = mapped_column(comment="Role of the message speaker")
    content: Mapped[str] = mapped_column(comment="Content of the message")


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

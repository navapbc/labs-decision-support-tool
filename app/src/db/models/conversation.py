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

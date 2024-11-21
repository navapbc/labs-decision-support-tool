import logging

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base, IdMixin

logger = logging.getLogger(__name__)


class ChatMessage(Base, IdMixin):
    __tablename__ = "chat_message"

    session_id: Mapped[str] = mapped_column(
        comment="Session ID that this message is associated with"
    )
    role: Mapped[str] = mapped_column(comment="Role of the message speaker")
    content: Mapped[str] = mapped_column(comment="Content of the message")
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False, comment="Used to order messages in a session"
    )

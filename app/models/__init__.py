"""
app/models/__init__.py
──────────────────────
Re-exports all ORM models so that Alembic's autogenerate
can discover them via a single import.
"""

from app.models.conversation import Conversation, Message, MessageRole, MessageType, ConversationStatus
from app.models.spare_part import SparePart, YouTubeCache
from app.models.user import User

__all__ = [
    "User",
    "Conversation",
    "Message",
    "MessageRole",
    "MessageType",
    "ConversationStatus",
    "SparePart",
    "YouTubeCache",
]

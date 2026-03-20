"""Episodic memory — conversation storage and full-text search.

Stores raw messages in PostgreSQL with metadata from the hot path.
Supports full-text search via GIN indexes and conversation lifecycle.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.conversations import Conversation, Message

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """Manages conversation storage and retrieval."""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def store_message(
        self,
        conversation_id: uuid_lib.UUID,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
        model_used: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_usd: Optional[float] = None,
        parent_message_id: Optional[uuid_lib.UUID] = None,
    ) -> Message:
        """Store a message in episodic memory (hot path)."""
        meta = metadata or {}
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model_used=model_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            parent_message_id=parent_message_id,
            memory_keywords=meta.get("keywords"),
            entities_extracted=meta.get("entities"),
        )
        self._db.add(msg)
        await self._db.flush()

        # Update conversation message count
        await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(message_count=Conversation.message_count + 1)
        )
        return msg

    async def get_messages(
        self,
        conversation_id: uuid_lib.UUID,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> list[Message]:
        """Get messages for a conversation, ordered by creation time."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        if before:
            query = query.where(Message.created_at < str(before))
        result = await self._db.execute(query)
        return list(reversed(result.scalars().all()))

    async def create_conversation(
        self,
        user_id: uuid_lib.UUID,
        title: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(user_id=user_id, title=title or "New Conversation")
        self._db.add(conv)
        await self._db.flush()
        return conv

    async def list_conversations(
        self,
        user_id: uuid_lib.UUID,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[Conversation]:
        """List conversations for a user, newest first."""
        query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        if not include_archived:
            query = query.where(Conversation.is_archived == False)  # noqa: E712
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def archive_conversation(self, conversation_id: uuid_lib.UUID) -> bool:
        """Soft-delete a conversation."""
        result = await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(is_archived=True)
        )
        return result.rowcount > 0

    async def rename_conversation(
        self, conversation_id: uuid_lib.UUID, title: str
    ) -> bool:
        """Update conversation title."""
        result = await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )
        return result.rowcount > 0

    async def update_summary(
        self, conversation_id: uuid_lib.UUID, summary: str, topics: list[str]
    ) -> None:
        """Set conversation summary and topics (warm path)."""
        await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(summary=summary, topics=topics)
        )

    async def search_conversations(
        self, user_id: uuid_lib.UUID, query: str, limit: int = 10
    ) -> list[dict]:
        """Full-text search across messages using PostgreSQL GIN index."""
        sql = text("""
            SELECT DISTINCT c.id, c.title, c.updated_at, c.summary,
                   ts_rank(to_tsvector('english', m.content),
                           plainto_tsquery('english', :query)) as rank
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = :user_id
              AND c.is_archived = false
              AND to_tsvector('english', m.content) @@
                  plainto_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        result = await self._db.execute(
            sql, {"user_id": str(user_id), "query": query, "limit": limit}
        )
        return [dict(row._mapping) for row in result]

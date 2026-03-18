from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.conversations import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(
        self,
        title: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Conversation:
        conv = Conversation(
            title=title,
            user_id=str(user_id) if user_id is not None else None,
        )
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def get_conversation(
        self, conversation_id: uuid.UUID
    ) -> Conversation | None:
        return await self.session.get(Conversation, str(conversation_id))

    async def list_conversations(
        self,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == str(user_id))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        model_used: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        metadata: dict | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=str(conversation_id),
            role=role,
            content=content,
            model_used=model_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            metadata_=metadata or {},
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_recent_messages(
        self, conversation_id: uuid.UUID, n: int = 20
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == str(conversation_id))
            .order_by(Message.created_at.desc())
            .limit(n)
        )
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

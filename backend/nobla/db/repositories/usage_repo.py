from __future__ import annotations

import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.usage import LLMUsage


class UsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_usage(
        self,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        conversation_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> LLMUsage:
        usage = LLMUsage(
            provider=provider,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            conversation_id=str(conversation_id) if conversation_id is not None else None,
            user_id=str(user_id) if user_id is not None else None,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_total_cost(
        self, user_id: uuid.UUID | None = None
    ) -> float:
        stmt = select(func.coalesce(func.sum(LLMUsage.cost_usd), 0))
        if user_id is not None:
            stmt = stmt.where(LLMUsage.user_id == str(user_id))
        result = await self.session.execute(stmt)
        return float(result.scalar())

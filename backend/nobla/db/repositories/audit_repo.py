from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from nobla.db.models.audit import AuditLog
from nobla.security.audit import AuditEntry


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, entry: AuditEntry) -> AuditLog:
        record = AuditLog(
            user_id=entry.user_id,
            action=entry.action,
            method=entry.method,
            tier=entry.tier,
            status=entry.status,
            ip_address=entry.ip_address,
            latency_ms=entry.latency_ms,
            metadata_=entry.metadata,
        )
        self.session.add(record)
        await self.session.flush()
        return record

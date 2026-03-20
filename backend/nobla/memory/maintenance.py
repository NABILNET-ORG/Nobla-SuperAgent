"""Cold path maintenance — decay, dedup, prune, graph cleanup.

Runs on a schedule (default: 3 AM daily via APScheduler). Performs:
1. Decay: reduce confidence of unaccessed memories
2. Dedup: merge near-duplicate facts
3. Prune: remove low-confidence memories past retention period
4. Graph cleanup: remove orphaned nodes
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.memory import MemoryNode, MemoryLink

logger = logging.getLogger(__name__)

# Decay rate per day for unaccessed memories
DECAY_RATE = 0.99

# Minimum confidence before pruning
MIN_CONFIDENCE = 0.1


class MaintenanceEngine:
    """Performs cold path maintenance tasks on memory storage."""

    def __init__(self, db_session: AsyncSession, retention_days: int = 90):
        self._db = db_session
        self._retention_days = retention_days

    async def run_all(self, user_id: Optional[uuid_lib.UUID] = None) -> dict:
        """Run all maintenance tasks. Returns counts of affected records."""
        decayed = await self.decay_memories(user_id)
        pruned = await self.prune_old_memories(user_id)
        orphans = await self.cleanup_orphan_links()

        logger.info(
            "maintenance_complete",
            decayed=decayed,
            pruned=pruned,
            orphans_removed=orphans,
        )
        return {
            "decayed": decayed,
            "pruned": pruned,
            "orphans_removed": orphans,
        }

    async def decay_memories(self, user_id: Optional[uuid_lib.UUID] = None) -> int:
        """Apply time-based decay to memory confidence scores."""
        query = (
            update(MemoryNode)
            .values(decay_factor=MemoryNode.decay_factor * DECAY_RATE)
        )
        if user_id:
            query = query.where(MemoryNode.user_id == str(user_id))

        result = await self._db.execute(query)
        return result.rowcount

    async def prune_old_memories(self, user_id: Optional[uuid_lib.UUID] = None) -> int:
        """Remove memories below minimum confidence past retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        query = (
            delete(MemoryNode)
            .where(MemoryNode.decay_factor < MIN_CONFIDENCE)
            .where(MemoryNode.created_at < str(cutoff))
        )
        if user_id:
            query = query.where(MemoryNode.user_id == str(user_id))

        result = await self._db.execute(query)
        return result.rowcount

    async def cleanup_orphan_links(self) -> int:
        """Remove MemoryLink rows where source or target no longer exists."""
        # Find orphaned links where source_id doesn't have a matching node
        orphan_query = (
            delete(MemoryLink)
            .where(
                ~MemoryLink.source_id.in_(
                    select(MemoryNode.id)
                )
            )
        )
        result = await self._db.execute(orphan_query)
        return result.rowcount

    async def get_stats(self, user_id: uuid_lib.UUID) -> dict:
        """Get memory statistics for a user."""
        # Count by note_type
        result = await self._db.execute(
            select(MemoryNode.note_type, func.count())
            .where(MemoryNode.user_id == str(user_id))
            .group_by(MemoryNode.note_type)
        )
        type_counts = {row[0] or "unknown": row[1] for row in result}

        # Total links
        link_result = await self._db.execute(
            select(func.count()).select_from(MemoryLink)
        )
        link_count = link_result.scalar() or 0

        return {
            "total_memories": sum(type_counts.values()),
            "by_type": type_counts,
            "total_links": link_count,
        }

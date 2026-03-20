"""Procedural memory — Bayesian workflow learning.

Tracks learned workflows (sequences of actions) with Bayesian scoring.
Each procedure has beta_success and beta_failure parameters that update
via Beta distribution: score = alpha / (alpha + beta).

Higher scores indicate more reliable procedures.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.memory import Procedure

logger = logging.getLogger(__name__)


def bayesian_score(alpha: float, beta: float) -> float:
    """Compute Bayesian score from Beta distribution parameters."""
    return alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5


class ProceduralMemory:
    """Manages learned workflows with Bayesian success scoring."""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def create_procedure(
        self,
        user_id: uuid_lib.UUID,
        name: str,
        description: Optional[str] = None,
        steps: Optional[list] = None,
        trigger_context: Optional[str] = None,
    ) -> str:
        """Create a new learned procedure."""
        proc = Procedure(
            user_id=str(user_id),
            name=name,
            description=description,
            steps=steps or [],
            trigger_context=trigger_context,
        )
        self._db.add(proc)
        await self._db.flush()

        logger.info("procedure_created", name=name, procedure_id=str(proc.id))
        return str(proc.id)

    async def record_outcome(
        self,
        procedure_id: uuid_lib.UUID,
        success: bool,
    ) -> None:
        """Record a success or failure for a procedure, updating Bayesian score."""
        if success:
            await self._db.execute(
                update(Procedure)
                .where(Procedure.id == str(procedure_id))
                .values(
                    beta_success=Procedure.beta_success + 1,
                    success_count=Procedure.success_count + 1,
                    bayesian_score=None,  # Will recompute on read
                )
            )
        else:
            await self._db.execute(
                update(Procedure)
                .where(Procedure.id == str(procedure_id))
                .values(
                    beta_failure=Procedure.beta_failure + 1,
                    failure_count=Procedure.failure_count + 1,
                    bayesian_score=None,
                )
            )

    async def get_relevant(
        self,
        user_id: uuid_lib.UUID,
        context: str,
        limit: int = 5,
    ) -> list[dict]:
        """Get procedures relevant to the current context, ranked by score."""
        result = await self._db.execute(
            select(Procedure)
            .where(Procedure.user_id == str(user_id))
            .order_by(desc(Procedure.bayesian_score))
            .limit(limit)
        )
        procedures = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "steps": p.steps,
                "score": bayesian_score(p.beta_success, p.beta_failure),
                "success_count": p.success_count,
                "failure_count": p.failure_count,
                "trigger_context": p.trigger_context,
            }
            for p in procedures
        ]

    async def list_procedures(
        self,
        user_id: uuid_lib.UUID,
        limit: int = 20,
    ) -> list[dict]:
        """List all procedures for a user."""
        result = await self._db.execute(
            select(Procedure)
            .where(Procedure.user_id == str(user_id))
            .order_by(desc(Procedure.updated_at))
            .limit(limit)
        )
        procedures = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "steps": p.steps,
                "score": bayesian_score(p.beta_success, p.beta_failure),
                "success_count": p.success_count,
                "failure_count": p.failure_count,
            }
            for p in procedures
        ]

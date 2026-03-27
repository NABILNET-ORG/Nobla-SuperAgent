"""TaskDecomposer — LLM-driven task decomposition and agent selection (Phase 6).

Breaks user instructions into a task graph. Heuristic fallback when
LLM is unavailable (same pattern as automation/interpreter.py).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from nobla.agents.models import AgentTask, TaskStatus

if TYPE_CHECKING:
    from nobla.agents.registry import AgentRegistry
    from nobla.brain.router import LLMRouter

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT = """You are a task decomposer for a multi-agent system.

Given a user instruction, break it into a list of tasks that agents can execute.
Available agents: {agents}

Each task has an "id" (short unique label like "t1", "t2") and an optional
"depends_on" list of ids it must wait for. Tasks without dependencies run in
parallel.

Return JSON:
{{"tasks": [{{"id": "t1", "instruction": "...", "agent": "agent_name", "depends_on": []}}]}}
Only return valid JSON, no other text.

User instruction: {instruction}"""


class TaskDecomposer:
    """Breaks instructions into task graphs and selects agents."""

    def __init__(
        self, router: LLMRouter, registry: AgentRegistry,
    ) -> None:
        self._router = router
        self._registry = registry

    async def decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        try:
            return await self._llm_decompose(instruction, workflow_id)
        except Exception as e:
            logger.warning("llm_decompose_failed, using heuristic: %s", e)
            return self._heuristic_decompose(instruction, workflow_id)

    async def _llm_decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        agents_desc = ", ".join(
            f"{c.name} ({c.description})"
            for c in self._registry.list_all()
        )
        prompt = DECOMPOSE_PROMPT.format(
            agents=agents_desc, instruction=instruction,
        )
        response = await self._router.route(prompt, tier="balanced")

        # Parse JSON response — build tasks then resolve dependency ids
        data = json.loads(response)
        raw_items = data.get("tasks", [])
        if not raw_items:
            return self._heuristic_decompose(instruction, workflow_id)

        # First pass: create tasks, map LLM-assigned id -> real task_id
        id_map: dict[str, str] = {}
        tasks: list[AgentTask] = []
        for item in raw_items:
            task = AgentTask(
                workflow_id=workflow_id,
                assigner="orchestrator",
                assignee=item.get("agent", ""),
                instruction=item.get("instruction", instruction),
            )
            llm_id = item.get("id", "")
            if llm_id:
                id_map[llm_id] = task.task_id
            tasks.append(task)

        # Second pass: resolve depends_on from LLM ids to real task_ids
        for item, task in zip(raw_items, tasks):
            for dep in item.get("depends_on", []):
                real_id = id_map.get(dep)
                if real_id:
                    task.depends_on.append(real_id)

        return tasks

    def _heuristic_decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        """Fallback: create a single task with the full instruction."""
        available = self._registry.list_all()
        assignee = available[0].name if available else ""
        return [
            AgentTask(
                workflow_id=workflow_id,
                assigner="orchestrator",
                assignee=assignee,
                instruction=instruction,
            )
        ]

    def select_agent(
        self, task: AgentTask, available: list[str],
    ) -> str:
        """Pick best agent by keyword matching instruction to description."""
        instruction_lower = task.instruction.lower()
        best_score = -1
        best_agent = available[0] if available else ""

        for name in available:
            entry = self._registry.get(name)
            if entry is None:
                continue
            _, config = entry
            words = config.description.lower().split()
            score = sum(1 for w in words if w in instruction_lower)
            if score > best_score:
                best_score = score
                best_agent = name
        return best_agent

"""AgentOrchestrator — workflow lifecycle and coordination (Phase 6).

Receives user requests, decomposes via TaskDecomposer, spawns agents,
assigns tasks via A2AProtocol, collects results, assembles final output.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nobla.agents.models import (
    AgentTask,
    TaskStatus,
    WorkflowState,
    topological_sort_tasks,
)
from nobla.events.models import NoblaEvent
from nobla.security.permissions import Tier

if TYPE_CHECKING:
    from nobla.agents.communication import A2AProtocol
    from nobla.agents.decomposer import TaskDecomposer
    from nobla.agents.executor import AgentExecutor
    from nobla.events.bus import NoblaEventBus
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Central coordinator for multi-agent workflows."""

    def __init__(
        self,
        executor: AgentExecutor,
        protocol: A2AProtocol,
        decomposer: TaskDecomposer,
        event_bus: NoblaEventBus,
        tool_registry: ToolRegistry,
        max_workflow_depth: int = 5,
        max_tasks_per_workflow: int = 20,
    ) -> None:
        self._executor = executor
        self._protocol = protocol
        self._decomposer = decomposer
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._max_workflow_depth = max_workflow_depth
        self._max_tasks = max_tasks_per_workflow
        self._active_workflows: dict[str, WorkflowState] = {}

    async def start(self) -> None:
        self._event_bus.subscribe(
            "agent.task.delegate", self._handle_delegation,
        )
        logger.info("orchestrator_started")

    async def stop(self) -> None:
        await self.kill_all_workflows()
        logger.info("orchestrator_stopped")

    async def run_workflow(
        self,
        instruction: str,
        user_id: str,
        user_tier: Tier,
        agent_team: list[str] | None = None,
        depth: int = 0,
    ) -> WorkflowState:
        workflow_id = str(uuid.uuid4())

        # Decompose instruction into tasks
        tasks = await self._decomposer.decompose(instruction, workflow_id)
        if len(tasks) > self._max_tasks:
            tasks = tasks[: self._max_tasks]

        task_graph = {t.task_id: t for t in tasks}

        workflow = WorkflowState(
            workflow_id=workflow_id,
            user_id=user_id,
            user_tier=user_tier,
            instruction=instruction,
            task_graph=task_graph,
            agent_assignments={},
            status="running",
            depth=depth,
            created_at=datetime.now(timezone.utc),
        )
        self._active_workflows[workflow_id] = workflow

        # Sort tasks into dependency tiers — each tier runs in parallel
        tiers = topological_sort_tasks(tasks)

        for tier in tiers:
            # Identify tasks whose dependencies all succeeded
            failed_ids = {
                t.task_id for t in task_graph.values()
                if t.status == TaskStatus.FAILED
            }
            runnable: list[AgentTask] = []
            for task in tier:
                if set(task.depends_on) & failed_ids:
                    task.status = TaskStatus.FAILED
                    logger.warning(
                        "task_skipped_dep_failed: %s", task.task_id,
                    )
                else:
                    runnable.append(task)

            if not runnable:
                continue

            # Execute all runnable tasks in this tier concurrently
            await asyncio.gather(*(
                self._execute_task(
                    task,
                    self._resolve_agent(task, agent_team),
                    user_tier, user_id, workflow,
                )
                for task in runnable
            ))

        # Determine workflow status
        statuses = [t.status for t in task_graph.values()]
        if all(s == TaskStatus.COMPLETED for s in statuses):
            workflow.status = "completed"
        elif any(s == TaskStatus.FAILED for s in statuses):
            workflow.status = "failed"
        else:
            workflow.status = "completed"

        self._active_workflows.pop(workflow_id, None)
        return workflow

    def _resolve_agent(
        self, task: AgentTask, team: list[str] | None,
    ) -> str:
        """Pick an agent name for *task* from team or registry."""
        if task.assignee:
            return task.assignee
        available = team or [
            c.name for c in self._decomposer._registry.list_all()
        ]
        return self._decomposer.select_agent(task, available)

    async def _execute_task(
        self,
        task: AgentTask,
        agent_name: str,
        user_tier: Tier,
        user_id: str,
        workflow: WorkflowState,
    ) -> None:
        """Spawn an agent, run *task*, stop agent. Safe for gather()."""
        try:
            agent = await self._executor.spawn(
                agent_name, user_tier=user_tier, user_id=user_id,
            )
            task.assignee = agent.instance_id
            workflow.agent_assignments[task.task_id] = agent.instance_id

            task.status = TaskStatus.RUNNING
            await self._protocol.send_task(
                "orchestrator", agent.instance_id, task,
            )
            try:
                result_task = await agent.handle_task(task)
                task.status = result_task.status
                task.artifacts = result_task.artifacts
                await self._protocol.send_result(agent.instance_id, task)
            except Exception as e:
                task.status = TaskStatus.FAILED
                await self._protocol.send_error(
                    agent.instance_id, task, str(e),
                )
                logger.error("task_failed: %s — %s", task.task_id, e)

            await self._executor.stop(
                agent.instance_id, reason="task_complete",
            )
        except (ValueError, PermissionError, RuntimeError) as e:
            task.status = TaskStatus.FAILED
            logger.error("agent_spawn_failed: %s", e)

    async def kill_workflow(self, workflow_id: str) -> None:
        workflow = self._active_workflows.pop(workflow_id, None)
        if workflow is None:
            return
        for instance_id in workflow.agent_assignments.values():
            await self._executor.kill(instance_id)
        workflow.status = "cancelled"

    async def kill_all_workflows(self) -> None:
        for wf_id in list(self._active_workflows.keys()):
            await self.kill_workflow(wf_id)

    # ── Delegation ──

    def _find_agent_depth(self, instance_id: str) -> int:
        """Return the workflow depth for *instance_id*, or 0 if unknown."""
        for wf in self._active_workflows.values():
            if instance_id in wf.agent_assignments.values():
                return wf.depth
        return 0

    def _find_agent_context(self, instance_id: str) -> tuple[str, Tier]:
        """Return (user_id, user_tier) from the workflow owning *instance_id*."""
        for wf in self._active_workflows.values():
            if instance_id in wf.agent_assignments.values():
                return wf.user_id, wf.user_tier
        return "system", Tier.STANDARD

    async def _handle_delegation(self, event: NoblaEvent) -> None:
        """Handle agent delegation requests with depth limiting."""
        payload = event.payload
        task_data = payload.get("task", {})
        if not task_data:
            return

        instruction = task_data.get("instruction", "")
        assigner = task_data.get("assigner", "")
        preferred = payload.get("preferred_target")

        # Depth check — prevent infinite delegation chains
        parent_depth = self._find_agent_depth(assigner)
        if parent_depth + 1 >= self._max_workflow_depth:
            logger.warning(
                "delegation_rejected_max_depth: depth=%d, instruction=%s",
                parent_depth, instruction,
            )
            return

        user_id, user_tier = self._find_agent_context(assigner)
        team = [preferred] if preferred else None

        try:
            sub = await self.run_workflow(
                instruction=instruction,
                user_id=user_id,
                user_tier=user_tier,
                agent_team=team,
                depth=parent_depth + 1,
            )
            logger.info(
                "delegation_completed: wf=%s status=%s depth=%d",
                sub.workflow_id, sub.status, sub.depth,
            )
        except Exception as exc:
            logger.error("delegation_failed: %s — %s", instruction, exc)

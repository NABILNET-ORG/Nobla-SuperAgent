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
            depth=0,
            created_at=datetime.now(timezone.utc),
        )
        self._active_workflows[workflow_id] = workflow

        # Spawn agents and assign tasks
        for task in tasks:
            agent_name = task.assignee
            if not agent_name:
                available = agent_team or [
                    c.name for c in self._decomposer._registry.list_all()
                ]
                agent_name = self._decomposer.select_agent(task, available)

            try:
                agent = await self._executor.spawn(
                    agent_name,
                    user_tier=user_tier,
                    user_id=user_id,
                )
                task.assignee = agent.instance_id
                workflow.agent_assignments[task.task_id] = agent.instance_id

                # Phase 6 v1: synchronous execution per task.
                # TODO(phase6-v2): Use protocol.send_task() + wait_for_result()
                # for async parallel execution across agents.
                task.status = TaskStatus.RUNNING
                try:
                    result_task = await agent.handle_task(task)
                    task.status = result_task.status
                    task.artifacts = result_task.artifacts
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    logger.error("task_failed: %s — %s", task.task_id, e)

                # Stop agent after task completes
                await self._executor.stop(agent.instance_id, reason="task_complete")

            except (ValueError, PermissionError, RuntimeError) as e:
                task.status = TaskStatus.FAILED
                logger.error("agent_spawn_failed: %s", e)

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

    async def _handle_delegation(self, event: NoblaEvent) -> None:
        """Handle agent delegation requests (depth-limited).

        Phase 6 v1: logs the delegation request. Full implementation
        (spawn sub-agent, check depth, assign via protocol) deferred to v2.
        TODO(phase6-v2): Implement full delegation with depth checking,
        agent selection, and async task assignment.
        """
        payload = event.payload
        task_data = payload.get("task", {})
        if not task_data:
            return
        logger.info("delegation_received: %s", task_data.get("instruction", ""))

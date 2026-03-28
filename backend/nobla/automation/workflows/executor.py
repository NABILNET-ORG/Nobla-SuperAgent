"""Workflow executor — DAG-based step execution engine (Phase 6).

Architecture:
    WorkflowExecutor receives a Workflow + WorkflowExecution, converts steps
    into topological tiers via Kahn's algorithm, then executes each tier
    concurrently with ``asyncio.gather()``.  Tiers execute sequentially.

    Supported step types:
        tool      — delegates to a ToolExecutor callback
        agent     — delegates to an AgentOrchestrator callback
        condition — evaluates named branches, enables/disables downstream steps
        webhook   — POSTs to external URL
        delay     — sleeps for configured duration
        approval  — pauses until user confirms (via callback)

    Error handling per step:
        fail     — mark step + execution failed, cascade dependents
        retry    — re-run up to max_retries with backoff
        continue — mark step failed, dependents still proceed
        skip     — skip step, dependents proceed
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from nobla.automation.workflows.models import (
    ConditionOperator,
    ErrorHandling,
    ExecutionStatus,
    StepExecution,
    StepType,
    TriggerCondition,
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    evaluate_conditions,
    resolve_field_path,
)

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

# Callback types for pluggable step execution
ToolCallback = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]
AgentCallback = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]
WebhookCallback = Callable[[str, bytes, dict[str, str]], Awaitable[dict[str, Any]]]
ApprovalCallback = Callable[[str, str, dict[str, Any]], Awaitable[bool]]


def topological_sort_steps(steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
    """Group workflow steps into execution tiers via Kahn's algorithm.

    Each tier is a list of steps whose dependencies are satisfied by all
    preceding tiers.  Steps within a tier can run in parallel.

    Raises ``ValueError`` on cycles or missing dependency references.
    """
    if not steps:
        return []

    by_id: dict[str, WorkflowStep] = {s.step_id: s for s in steps}
    valid_ids = set(by_id)

    for s in steps:
        bad = set(s.depends_on) - valid_ids
        if bad:
            raise ValueError(
                f"Step {s.step_id!r} depends on unknown steps: {bad}"
            )

    in_degree: dict[str, int] = {s.step_id: 0 for s in steps}
    dependents: dict[str, list[str]] = {s.step_id: [] for s in steps}
    for s in steps:
        for dep_id in s.depends_on:
            in_degree[s.step_id] += 1
            dependents[dep_id].append(s.step_id)

    tiers: list[list[WorkflowStep]] = []
    ready = [sid for sid, deg in in_degree.items() if deg == 0]

    visited = 0
    while ready:
        tier = [by_id[sid] for sid in ready]
        tiers.append(tier)
        visited += len(tier)
        next_ready: list[str] = []
        for sid in ready:
            for child in dependents[sid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_ready.append(child)
        ready = next_ready

    if visited != len(steps):
        raise ValueError("Cycle detected in step dependency graph")

    return tiers


class WorkflowExecutor:
    """Executes workflow steps as a DAG with parallel tiers.

    Args:
        event_bus: For emitting lifecycle events.
        tool_callback: Async function to execute tool steps.
        agent_callback: Async function to execute agent steps.
        webhook_callback: Async function to POST webhook steps.
        approval_callback: Async function to request user approval.
    """

    def __init__(
        self,
        event_bus: NoblaEventBus | None = None,
        tool_callback: ToolCallback | None = None,
        agent_callback: AgentCallback | None = None,
        webhook_callback: WebhookCallback | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._tool_cb = tool_callback
        self._agent_cb = agent_callback
        self._webhook_cb = webhook_callback
        self._approval_cb = approval_callback

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def execute(
        self, workflow: Workflow, execution: WorkflowExecution
    ) -> WorkflowExecution:
        """Execute a workflow's steps as a DAG.

        Updates the execution in-place and returns it.
        """
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.now(timezone.utc)
        execution.workflow_version = workflow.version

        await self._emit(
            "workflow.execution.started", workflow, execution
        )

        steps = workflow.steps
        if not steps:
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)
            await self._emit(
                "workflow.execution.completed", workflow, execution
            )
            return execution

        # Initialize step executions
        for step in steps:
            execution.step_executions[step.step_id] = StepExecution(
                execution_id=execution.execution_id,
                step_id=step.step_id,
            )

        try:
            tiers = topological_sort_steps(steps)
        except ValueError as e:
            execution.status = ExecutionStatus.FAILED
            execution.completed_at = datetime.now(timezone.utc)
            logger.error("workflow_sort_failed wf=%s: %s", workflow.workflow_id, e)
            await self._emit(
                "workflow.execution.failed", workflow, execution
            )
            return execution

        # Track which steps are disabled (by condition branches not taken)
        disabled_steps: set[str] = set()
        failed_steps: set[str] = set()

        for tier in tiers:
            tasks = []
            for step in tier:
                if step.step_id in disabled_steps:
                    se = execution.step_executions[step.step_id]
                    se.status = ExecutionStatus.SKIPPED
                    await self._emit_step(
                        "workflow.step.skipped", workflow, execution, step
                    )
                    continue

                # Check if any dependency failed (cascade)
                dep_failed = any(
                    d in failed_steps for d in step.depends_on
                )
                if dep_failed and step.error_handling == ErrorHandling.FAIL:
                    se = execution.step_executions[step.step_id]
                    se.status = ExecutionStatus.FAILED
                    se.error = "Dependency failed (cascade)"
                    failed_steps.add(step.step_id)
                    await self._emit_step(
                        "workflow.step.failed", workflow, execution, step
                    )
                    continue

                tasks.append(
                    self._execute_step(
                        step, workflow, execution,
                        disabled_steps, failed_steps,
                    )
                )

            if tasks:
                await asyncio.gather(*tasks)

        # Determine final status
        has_failures = any(
            se.status == ExecutionStatus.FAILED
            for se in execution.step_executions.values()
        )
        execution.status = (
            ExecutionStatus.FAILED if has_failures else ExecutionStatus.COMPLETED
        )
        execution.completed_at = datetime.now(timezone.utc)

        final_event = (
            "workflow.execution.failed"
            if has_failures
            else "workflow.execution.completed"
        )
        await self._emit(final_event, workflow, execution)
        return execution

    # ------------------------------------------------------------------
    # Step execution with error handling
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: WorkflowStep,
        workflow: Workflow,
        execution: WorkflowExecution,
        disabled_steps: set[str],
        failed_steps: set[str],
    ) -> None:
        """Execute a single step with error handling and retries."""
        se = execution.step_executions[step.step_id]
        se.status = ExecutionStatus.RUNNING
        se.started_at = datetime.now(timezone.utc)
        await self._emit_step(
            "workflow.step.started", workflow, execution, step
        )

        max_attempts = (
            step.max_retries + 1
            if step.error_handling == ErrorHandling.RETRY
            else 1
        )

        last_error = ""
        for attempt in range(max_attempts):
            try:
                result = await self._run_step(step, execution)
                se.status = ExecutionStatus.COMPLETED
                se.result = result
                se.completed_at = datetime.now(timezone.utc)

                # Handle condition branches
                if step.type == StepType.CONDITION:
                    self._apply_condition_branches(
                        step, result, execution, disabled_steps
                    )
                    se.branch_taken = result.get("branch_taken")

                await self._emit_step(
                    "workflow.step.completed", workflow, execution, step
                )
                return

            except Exception as e:
                last_error = str(e)
                if attempt < max_attempts - 1:
                    delay = 2.0 * (2 ** attempt)
                    logger.warning(
                        "workflow_step_retry step=%s attempt=%d delay=%.1f",
                        step.step_id, attempt + 1, delay,
                    )
                    await asyncio.sleep(delay)

        # All attempts failed
        se.error = last_error
        se.completed_at = datetime.now(timezone.utc)

        if step.error_handling == ErrorHandling.SKIP:
            se.status = ExecutionStatus.SKIPPED
            await self._emit_step(
                "workflow.step.skipped", workflow, execution, step
            )
        elif step.error_handling == ErrorHandling.CONTINUE:
            se.status = ExecutionStatus.FAILED
            await self._emit_step(
                "workflow.step.failed", workflow, execution, step
            )
            # Don't add to failed_steps — dependents still proceed
        else:
            # FAIL or exhausted RETRY
            se.status = ExecutionStatus.FAILED
            failed_steps.add(step.step_id)
            await self._emit_step(
                "workflow.step.failed", workflow, execution, step
            )

    # ------------------------------------------------------------------
    # Step type dispatch
    # ------------------------------------------------------------------

    async def _run_step(
        self, step: WorkflowStep, execution: WorkflowExecution
    ) -> dict[str, Any]:
        """Dispatch to the appropriate step type handler."""
        if step.type == StepType.TOOL:
            return await self._run_tool(step, execution)
        if step.type == StepType.AGENT:
            return await self._run_agent(step, execution)
        if step.type == StepType.CONDITION:
            return self._run_condition(step, execution)
        if step.type == StepType.WEBHOOK:
            return await self._run_webhook(step)
        if step.type == StepType.DELAY:
            return await self._run_delay(step)
        if step.type == StepType.APPROVAL:
            return await self._run_approval(step, execution)
        raise ValueError(f"Unknown step type: {step.type}")

    async def _run_tool(
        self, step: WorkflowStep, execution: WorkflowExecution
    ) -> dict[str, Any]:
        """Execute a tool step."""
        if not self._tool_cb:
            raise RuntimeError("No tool callback configured")
        return await self._tool_cb(step.config, execution.user_id)

    async def _run_agent(
        self, step: WorkflowStep, execution: WorkflowExecution
    ) -> dict[str, Any]:
        """Execute an agent step."""
        if not self._agent_cb:
            raise RuntimeError("No agent callback configured")
        return await self._agent_cb(step.config, execution.user_id)

    def _run_condition(
        self, step: WorkflowStep, execution: WorkflowExecution
    ) -> dict[str, Any]:
        """Evaluate a condition step's branches."""
        cc = step.get_condition_config()
        if not cc:
            return {"branch_taken": None, "matched": False}

        # Build context from previous step results
        context: dict[str, Any] = {}
        for sid, se in execution.step_executions.items():
            if se.status == ExecutionStatus.COMPLETED:
                context[sid] = se.result
                # Also flatten with step name prefix
                for step_def in []:
                    pass
        # Flatten all step results into context
        for sid, se in execution.step_executions.items():
            if se.status == ExecutionStatus.COMPLETED and se.result:
                for k, v in se.result.items():
                    context[f"{sid}.result.{k}"] = v
                    context[k] = v  # Also top-level for convenience

        branch = cc.evaluate(context)
        if branch:
            return {
                "branch_taken": branch.name,
                "matched": True,
                "next_steps": branch.next_steps,
            }
        return {"branch_taken": None, "matched": False}

    async def _run_webhook(self, step: WorkflowStep) -> dict[str, Any]:
        """POST to an external URL."""
        if not self._webhook_cb:
            raise RuntimeError("No webhook callback configured")
        url = step.config.get("url", "")
        payload = json.dumps(step.config.get("payload", {})).encode("utf-8")
        headers = step.config.get("headers", {"Content-Type": "application/json"})
        return await self._webhook_cb(url, payload, headers)

    async def _run_delay(self, step: WorkflowStep) -> dict[str, Any]:
        """Sleep for configured duration."""
        seconds = step.config.get("seconds", 0)
        if seconds > 0:
            await asyncio.sleep(seconds)
        return {"delayed_seconds": seconds}

    async def _run_approval(
        self, step: WorkflowStep, execution: WorkflowExecution
    ) -> dict[str, Any]:
        """Request user approval."""
        if not self._approval_cb:
            raise RuntimeError("No approval callback configured")
        message = step.config.get("message", "Approval required")
        approved = await self._approval_cb(
            execution.user_id, message, step.config
        )
        if not approved:
            raise RuntimeError("Approval denied by user")
        return {"approved": True}

    # ------------------------------------------------------------------
    # Condition branch application
    # ------------------------------------------------------------------

    def _apply_condition_branches(
        self,
        step: WorkflowStep,
        result: dict[str, Any],
        execution: WorkflowExecution,
        disabled_steps: set[str],
    ) -> None:
        """After a condition evaluates, disable steps not on the taken branch."""
        cc = step.get_condition_config()
        if not cc:
            return

        taken_next = set(result.get("next_steps", []))

        # Collect ALL next_steps from ALL branches
        all_branch_steps: set[str] = set()
        for branch in cc.branches:
            all_branch_steps.update(branch.next_steps)

        # Disable steps in non-taken branches
        not_taken = all_branch_steps - taken_next
        disabled_steps.update(not_taken)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit(
        self,
        event_type: str,
        workflow: Workflow,
        execution: WorkflowExecution,
    ) -> None:
        """Emit a workflow-level event."""
        if not self._event_bus:
            return
        from nobla.events.models import NoblaEvent

        await self._event_bus.emit(
            NoblaEvent(
                event_type=event_type,
                source=f"workflow.{workflow.workflow_id}",
                payload={
                    "workflow_id": workflow.workflow_id,
                    "execution_id": execution.execution_id,
                    "workflow_version": execution.workflow_version,
                    "status": execution.status.value,
                },
                user_id=execution.user_id,
            )
        )

    async def _emit_step(
        self,
        event_type: str,
        workflow: Workflow,
        execution: WorkflowExecution,
        step: WorkflowStep,
    ) -> None:
        """Emit a step-level event."""
        if not self._event_bus:
            return
        from nobla.events.models import NoblaEvent

        se = execution.step_executions.get(step.step_id)
        await self._event_bus.emit(
            NoblaEvent(
                event_type=event_type,
                source=f"workflow.{workflow.workflow_id}",
                payload={
                    "workflow_id": workflow.workflow_id,
                    "execution_id": execution.execution_id,
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "step_type": step.type.value,
                    "status": se.status.value if se else "unknown",
                },
                user_id=execution.user_id,
            )
        )

"""Workflow service — orchestrates CRUD, versioning, triggers, execution (Phase 6).

Central coordinator that ties together WorkflowInterpreter, TriggerMatcher,
WorkflowExecutor, and in-memory storage.  Gateway handlers delegate to this.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from nobla.automation.workflows.models import (
    ExecutionStatus,
    TriggerCondition,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
)
from nobla.automation.workflows.templates import (
    TemplateStep,
    TemplateTrigger,
    WorkflowExportData,
    WorkflowTemplate,
    workflow_step_to_template_step,
    workflow_trigger_to_template_trigger,
)

if TYPE_CHECKING:
    from nobla.automation.workflows.executor import WorkflowExecutor
    from nobla.automation.workflows.interpreter import WorkflowInterpreter
    from nobla.automation.workflows.trigger_matcher import TriggerMatcher
    from nobla.events.bus import NoblaEventBus
    from nobla.events.models import NoblaEvent

logger = logging.getLogger(__name__)


class WorkflowService:
    """Orchestrates workflow lifecycle — create, edit, trigger, execute.

    Args:
        executor: DAG step executor.
        interpreter: NL-to-workflow parser.
        trigger_matcher: Event pattern matcher.
        event_bus: For emitting service-level events.
        max_workflows_per_user: Registration limit.
        max_concurrent_executions: Parallel execution limit.
    """

    def __init__(
        self,
        executor: WorkflowExecutor,
        interpreter: WorkflowInterpreter,
        trigger_matcher: TriggerMatcher,
        event_bus: NoblaEventBus | None = None,
        max_workflows_per_user: int = 100,
        max_concurrent_executions: int = 5,
    ) -> None:
        self._executor = executor
        self._interpreter = interpreter
        self._matcher = trigger_matcher
        self._event_bus = event_bus
        self._max_per_user = max_workflows_per_user
        self._max_concurrent = max_concurrent_executions

        # In-memory stores
        self._workflows: dict[str, Workflow] = {}
        self._executions: dict[str, list[WorkflowExecution]] = {}  # workflow_id → execs
        self._active_executions: int = 0

        # Wire trigger matcher callback
        self._matcher.set_callback(self._on_trigger_matched)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the trigger matcher."""
        await self._matcher.start()
        logger.info("workflow_service_started")

    async def stop(self) -> None:
        """Stop the trigger matcher."""
        await self._matcher.stop()
        logger.info("workflow_service_stopped")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_from_nl(
        self, description: str, user_id: str, name: str = "",
    ) -> Workflow:
        """Create a workflow from natural language.

        Raises:
            ValueError: If user limit reached.
        """
        self._check_user_limit(user_id)
        wf = await self._interpreter.interpret(description, user_id, name)
        self._store(wf)
        logger.info("workflow_created id=%s name=%s", wf.workflow_id, wf.name)
        return wf

    def create(self, workflow: Workflow) -> Workflow:
        """Register a pre-built workflow.

        Raises:
            ValueError: If user limit reached.
        """
        self._check_user_limit(workflow.user_id)
        self._store(workflow)
        return workflow

    def get(self, workflow_id: str) -> Workflow:
        """Retrieve a workflow by ID.

        Raises:
            KeyError: If not found.
        """
        try:
            return self._workflows[workflow_id]
        except KeyError:
            raise KeyError(f"Workflow not found: {workflow_id}") from None

    def list_for_user(self, user_id: str) -> list[Workflow]:
        """List all workflows for a user."""
        return [
            wf for wf in self._workflows.values()
            if wf.user_id == user_id
        ]

    def delete(self, workflow_id: str) -> None:
        """Delete a workflow and unregister its triggers.

        Raises:
            KeyError: If not found.
        """
        self.get(workflow_id)  # Validate exists
        self._matcher.unregister_workflow(workflow_id)
        del self._workflows[workflow_id]
        self._executions.pop(workflow_id, None)
        logger.info("workflow_deleted id=%s", workflow_id)

    # ------------------------------------------------------------------
    # Update + versioning
    # ------------------------------------------------------------------

    def update(
        self,
        workflow_id: str,
        new_steps: list[WorkflowStep] | None = None,
        new_triggers: list[WorkflowTrigger] | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> Workflow:
        """Update a workflow — bumps version automatically.

        Raises:
            KeyError: If not found.
        """
        wf = self.get(workflow_id)
        wf.bump_version(new_steps=new_steps, new_triggers=new_triggers)
        if name is not None:
            wf.name = name
        if description is not None:
            wf.description = description

        # Re-register triggers
        self._matcher.unregister_workflow(workflow_id)
        if wf.status == WorkflowStatus.ACTIVE:
            self._matcher.register_workflow_triggers(workflow_id, wf.triggers)

        logger.info("workflow_updated id=%s version=%d", workflow_id, wf.version)
        return wf

    def update_status(self, workflow_id: str, status: WorkflowStatus) -> Workflow:
        """Pause/resume/archive a workflow.

        Raises:
            KeyError: If not found.
        """
        wf = self.get(workflow_id)
        wf.status = status
        wf.updated_at = datetime.now(timezone.utc)

        # Toggle triggers
        self._matcher.unregister_workflow(workflow_id)
        if status == WorkflowStatus.ACTIVE:
            self._matcher.register_workflow_triggers(workflow_id, wf.triggers)

        logger.info("workflow_status_updated id=%s status=%s", workflow_id, status.value)
        return wf

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def trigger_manually(self, workflow_id: str, user_id: str = "") -> WorkflowExecution:
        """Manually trigger a workflow execution.

        Raises:
            KeyError: If workflow not found.
            ValueError: If workflow not active or concurrent limit reached.
        """
        wf = self.get(workflow_id)
        if wf.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Workflow {workflow_id} is not active")
        return await self._start_execution(wf, user_id=user_id or wf.user_id)

    async def _on_trigger_matched(
        self, workflow_id: str, trigger: WorkflowTrigger, event: NoblaEvent,
    ) -> None:
        """Callback from TriggerMatcher when an event matches."""
        try:
            wf = self.get(workflow_id)
        except KeyError:
            logger.warning("trigger_matched_unknown_workflow id=%s", workflow_id)
            return

        if wf.status != WorkflowStatus.ACTIVE:
            return

        trigger_data = {
            "event_type": event.event_type,
            "source": event.source,
            "payload": event.payload,
            "correlation_id": event.correlation_id,
        }
        await self._start_execution(
            wf, user_id=event.user_id or wf.user_id,
            trigger_event=trigger_data,
        )

    async def _start_execution(
        self,
        wf: Workflow,
        user_id: str = "",
        trigger_event: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        """Create and run a workflow execution."""
        if self._active_executions >= self._max_concurrent:
            raise ValueError(
                f"Concurrent execution limit reached ({self._max_concurrent})"
            )

        execution = WorkflowExecution(
            workflow_id=wf.workflow_id,
            workflow_version=wf.version,
            user_id=user_id,
            trigger_event=trigger_event,
        )
        self._executions.setdefault(wf.workflow_id, []).append(execution)
        self._active_executions += 1

        try:
            await self._executor.execute(wf, execution)
        finally:
            self._active_executions -= 1

        return execution

    def get_executions(
        self, workflow_id: str, limit: int = 20,
    ) -> list[WorkflowExecution]:
        """Get recent executions for a workflow."""
        execs = self._executions.get(workflow_id, [])
        return list(execs[-limit:])

    def get_execution(self, workflow_id: str, execution_id: str) -> WorkflowExecution:
        """Get a specific execution.

        Raises:
            KeyError: If not found.
        """
        for ex in self._executions.get(workflow_id, []):
            if ex.execution_id == execution_id:
                return ex
        raise KeyError(f"Execution not found: {execution_id}")

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_workflow(
        self, workflow_id: str, include_metadata: bool = True,
    ) -> WorkflowExportData:
        """Export a workflow as portable data for sharing/backup.

        Strips runtime UUIDs and replaces them with short ref_ids.

        Raises:
            KeyError: If workflow not found.
        """
        wf = self.get(workflow_id)

        # Build UUID → ref_id mapping for step cross-references
        ref_id_map: dict[str, str] = {}
        used_refs: set[str] = set()
        for step in wf.steps:
            ref = step.name.lower().replace(" ", "_").replace("-", "_")
            ref = "".join(c for c in ref if c.isalnum() or c == "_")
            ref = ref or f"step_{step.step_id[:8]}"
            # Deduplicate
            base = ref
            counter = 2
            while ref in used_refs:
                ref = f"{base}_{counter}"
                counter += 1
            used_refs.add(ref)
            ref_id_map[step.step_id] = ref

        steps = [
            workflow_step_to_template_step(s, ref_id_map) for s in wf.steps
        ]
        triggers = [
            workflow_trigger_to_template_trigger(t) for t in wf.triggers
        ]

        metadata: dict[str, Any] = {}
        if include_metadata:
            metadata = {
                "status": wf.status.value,
                "version": wf.version,
                "user_id": wf.user_id,
            }

        return WorkflowExportData(
            source_workflow_id=wf.workflow_id,
            source_workflow_version=wf.version,
            name=wf.name,
            description=wf.description,
            steps=steps,
            triggers=triggers,
            metadata=metadata,
        )

    def import_workflow(
        self, export_data: WorkflowExportData, user_id: str,
        name_override: str | None = None,
    ) -> Workflow:
        """Import a workflow from portable export data.

        Assigns fresh UUIDs to all steps and triggers, then registers
        the workflow under the given user.

        Raises:
            ValueError: If user limit reached or data is invalid.
        """
        self._check_user_limit(user_id)

        wf_name = name_override or export_data.name
        if not wf_name:
            raise ValueError("Workflow name is required")

        wf = Workflow(
            user_id=user_id,
            name=wf_name,
            description=export_data.description,
        )

        # Map ref_ids to fresh UUIDs
        ref_to_uuid: dict[str, str] = {}
        for ts in export_data.steps:
            ref_to_uuid[ts.ref_id] = str(_uuid.uuid4())

        # Hydrate steps with real UUIDs
        steps: list[WorkflowStep] = []
        for ts in export_data.steps:
            step = WorkflowStep(
                step_id=ref_to_uuid[ts.ref_id],
                workflow_id=wf.workflow_id,
                workflow_version=1,
                name=ts.name,
                type=_parse_step_type(ts.type),
                config=ts.config.copy(),
                depends_on=[
                    ref_to_uuid.get(dep, dep) for dep in ts.depends_on
                ],
                error_handling=_parse_error_handling(ts.error_handling),
                max_retries=ts.max_retries,
                timeout_seconds=ts.timeout_seconds,
            )
            steps.append(step)
        wf.steps = steps

        # Hydrate triggers
        triggers: list[WorkflowTrigger] = []
        for tt in export_data.triggers:
            conditions = [
                TriggerCondition(
                    field_path=c.get("field_path", ""),
                    operator=_parse_condition_operator(c.get("operator", "eq")),
                    value=c.get("value"),
                )
                for c in tt.conditions
            ]
            trigger = WorkflowTrigger(
                workflow_id=wf.workflow_id,
                event_pattern=tt.event_pattern,
                conditions=conditions,
            )
            triggers.append(trigger)
        wf.triggers = triggers

        self._store(wf)
        logger.info(
            "workflow_imported id=%s name=%s from=%s",
            wf.workflow_id, wf.name, export_data.source_workflow_id,
        )
        return wf

    def instantiate_template(
        self, template: WorkflowTemplate, user_id: str,
        name_override: str | None = None,
    ) -> Workflow:
        """Create a live workflow from a template.

        Convenience wrapper — converts template to export format
        then imports it.

        Raises:
            ValueError: If user limit reached.
        """
        export_data = WorkflowExportData(
            name=template.name,
            description=template.description,
            steps=template.steps,
            triggers=template.triggers,
            metadata={"template_id": template.template_id},
        )
        return self.import_workflow(
            export_data, user_id, name_override=name_override,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_user_limit(self, user_id: str) -> None:
        count = sum(1 for wf in self._workflows.values() if wf.user_id == user_id)
        if count >= self._max_per_user:
            raise ValueError(
                f"User {user_id} has reached the maximum of "
                f"{self._max_per_user} workflows"
            )

    def _store(self, wf: Workflow) -> None:
        """Store workflow and register its triggers."""
        self._workflows[wf.workflow_id] = wf
        self._executions.setdefault(wf.workflow_id, [])
        if wf.status == WorkflowStatus.ACTIVE:
            self._matcher.register_workflow_triggers(wf.workflow_id, wf.triggers)


# ---------------------------------------------------------------------------
# Module-level helpers for enum parsing
# ---------------------------------------------------------------------------

def _parse_step_type(value: str) -> "StepType":
    """Parse a step type string into the enum."""
    from nobla.automation.workflows.models import StepType
    try:
        return StepType(value)
    except ValueError:
        return StepType.TOOL


def _parse_error_handling(value: str) -> "ErrorHandling":
    """Parse an error handling string into the enum."""
    from nobla.automation.workflows.models import ErrorHandling
    try:
        return ErrorHandling(value)
    except ValueError:
        return ErrorHandling.FAIL


def _parse_condition_operator(value: str) -> "ConditionOperator":
    """Parse a condition operator string into the enum."""
    from nobla.automation.workflows.models import ConditionOperator
    try:
        return ConditionOperator(value)
    except ValueError:
        return ConditionOperator.EQ

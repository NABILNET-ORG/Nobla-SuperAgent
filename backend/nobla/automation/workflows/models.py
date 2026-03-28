"""Workflow data models — definitions, triggers, executions, versioning (Phase 6).

Core models:
    Workflow          — Versioned workflow definition
    WorkflowStep      — Single step in the DAG (tool, agent, condition, etc.)
    WorkflowTrigger   — Activation rule (event pattern + conditions)
    TriggerCondition  — Payload filter (field_path op value)
    ConditionBranch   — Named branch for condition steps
    WorkflowExecution — Runtime instance of a workflow run
    StepExecution     — Per-step result within an execution
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow definition."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class StepType(str, Enum):
    """Type of workflow step."""

    TOOL = "tool"
    AGENT = "agent"
    CONDITION = "condition"
    WEBHOOK = "webhook"
    DELAY = "delay"
    APPROVAL = "approval"


class ErrorHandling(str, Enum):
    """Per-step error handling strategy."""

    FAIL = "fail"        # Mark step + execution failed, cascade to dependents
    RETRY = "retry"      # Re-run up to max_retries with backoff
    CONTINUE = "continue"  # Mark step failed, dependents still proceed
    SKIP = "skip"        # Skip step entirely, dependents proceed


class ExecutionStatus(str, Enum):
    """Runtime status of a workflow or step execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConditionOperator(str, Enum):
    """Operators for trigger conditions and condition steps."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"
    EXISTS = "exists"


# ---------------------------------------------------------------------------
# Trigger models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TriggerCondition:
    """Payload filter — evaluated against event data.

    Attributes:
        field_path: Dot-notation path into payload (e.g. "payload.branch").
        operator: Comparison operator.
        value: Expected value (ignored for 'exists' operator).
    """

    field_path: str = ""
    operator: ConditionOperator = ConditionOperator.EQ
    value: Any = None


@dataclass(slots=True)
class WorkflowTrigger:
    """Activation rule for a workflow — event pattern + conditions.

    Multiple triggers per workflow are supported (OR logic between triggers,
    AND logic between conditions within a trigger).

    Attributes:
        trigger_id: Unique identifier.
        workflow_id: Parent workflow.
        event_pattern: fnmatch-compatible pattern (e.g. "webhook.github.*").
        conditions: All must pass for this trigger to fire (AND logic).
        active: Whether this trigger is enabled.
    """

    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    event_pattern: str = "*"
    conditions: list[TriggerCondition] = field(default_factory=list)
    active: bool = True


# ---------------------------------------------------------------------------
# Condition branch model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ConditionBranch:
    """Named branch within a condition step.

    Attributes:
        name: Branch identifier (e.g. "tests_passed", "tests_failed").
        condition: Field/op/value to evaluate.
        next_steps: Step IDs activated when this branch is taken.
    """

    name: str = ""
    condition: TriggerCondition = field(default_factory=TriggerCondition)
    next_steps: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConditionConfig:
    """Configuration for a condition step — multiple named branches.

    Attributes:
        branches: Ordered list of branches; first match wins.
        default_branch: Fallback branch name if none match.
    """

    branches: list[ConditionBranch] = field(default_factory=list)
    default_branch: str = ""

    def evaluate(self, context: dict[str, Any]) -> ConditionBranch | None:
        """Evaluate branches against context, return first match or default."""
        for branch in self.branches:
            if _evaluate_condition(branch.condition, context):
                return branch
        # Fallback to default branch
        if self.default_branch:
            for branch in self.branches:
                if branch.name == self.default_branch:
                    return branch
        return None


# ---------------------------------------------------------------------------
# Step model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkflowStep:
    """Single step in the workflow DAG.

    Attributes:
        step_id: Unique identifier.
        workflow_id: Parent workflow.
        workflow_version: Version this step belongs to.
        name: Human-readable step name.
        type: Step type (tool, agent, condition, webhook, delay, approval).
        config: Type-specific configuration dict.
        depends_on: Step IDs this step depends on (DAG edges).
        error_handling: Strategy when this step fails.
        max_retries: Max retry attempts (for error_handling=retry).
        timeout_seconds: Max execution time (None = no limit).
        nl_source: Original NL text fragment that generated this step.
    """

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_version: int = 1
    name: str = ""
    type: StepType = StepType.TOOL
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    error_handling: ErrorHandling = ErrorHandling.FAIL
    max_retries: int = 0
    timeout_seconds: int | None = None
    nl_source: str | None = None

    def get_condition_config(self) -> ConditionConfig | None:
        """Parse config as ConditionConfig if this is a condition step."""
        if self.type != StepType.CONDITION:
            return None
        branches_raw = self.config.get("branches", [])
        branches = []
        for b in branches_raw:
            cond_raw = b.get("condition", {})
            cond = TriggerCondition(
                field_path=cond_raw.get("field", ""),
                operator=ConditionOperator(cond_raw.get("op", "eq")),
                value=cond_raw.get("value"),
            )
            branches.append(ConditionBranch(
                name=b.get("name", ""),
                condition=cond,
                next_steps=b.get("next_steps", []),
            ))
        return ConditionConfig(
            branches=branches,
            default_branch=self.config.get("default_branch", ""),
        )


# ---------------------------------------------------------------------------
# Workflow definition (versioned)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Workflow:
    """Versioned workflow definition.

    Every edit increments ``version``.  Steps and triggers are stored
    per-version so old versions remain queryable for audit/rollback.

    Attributes:
        workflow_id: Unique identifier.
        user_id: Owner.
        name: Human-readable name.
        description: What this workflow does.
        version: Current version (starts at 1, increments on edit).
        status: Lifecycle status.
        steps: Current version's steps.
        triggers: Current version's triggers.
        created_at: Initial creation timestamp.
        updated_at: Last modification timestamp.
    """

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: str = ""
    description: str = ""
    version: int = 1
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    steps: list[WorkflowStep] = field(default_factory=list)
    triggers: list[WorkflowTrigger] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # --- Version history (list of (version, steps, triggers) snapshots) ---
    _version_history: list[tuple[int, list[WorkflowStep], list[WorkflowTrigger]]] = field(
        default_factory=list, repr=False
    )

    def bump_version(
        self,
        new_steps: list[WorkflowStep] | None = None,
        new_triggers: list[WorkflowTrigger] | None = None,
    ) -> int:
        """Snapshot current state and increment version.

        Args:
            new_steps: Replacement steps (None keeps current).
            new_triggers: Replacement triggers (None keeps current).

        Returns:
            The new version number.
        """
        # Snapshot current version
        self._version_history.append((
            self.version,
            copy.deepcopy(self.steps),
            copy.deepcopy(self.triggers),
        ))
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)

        if new_steps is not None:
            for step in new_steps:
                step.workflow_version = self.version
            self.steps = new_steps
        else:
            for step in self.steps:
                step.workflow_version = self.version

        if new_triggers is not None:
            self.triggers = new_triggers

        return self.version

    def get_version(self, version: int) -> tuple[list[WorkflowStep], list[WorkflowTrigger]] | None:
        """Retrieve steps and triggers for a specific version.

        Returns None if the version doesn't exist.
        """
        if version == self.version:
            return self.steps, self.triggers
        for v, steps, triggers in self._version_history:
            if v == version:
                return steps, triggers
        return None

    def list_versions(self) -> list[int]:
        """Return all available version numbers."""
        versions = [v for v, _, _ in self._version_history]
        versions.append(self.version)
        return sorted(versions)


# ---------------------------------------------------------------------------
# Execution models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StepExecution:
    """Runtime result of a single step within a workflow execution.

    Attributes:
        id: Unique identifier.
        execution_id: Parent workflow execution.
        step_id: Which step this ran.
        status: Current execution status.
        result: Output data on success.
        error: Error message on failure.
        branch_taken: For condition steps — which branch was selected.
        started_at: When execution began.
        completed_at: When execution finished.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str = ""
    step_id: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    branch_taken: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class WorkflowExecution:
    """Runtime instance of a workflow run.

    Attributes:
        execution_id: Unique identifier.
        workflow_id: Which workflow this executes.
        workflow_version: Which version was executed.
        user_id: Who triggered this.
        trigger_event: The event that triggered this (None for manual).
        status: Current execution status.
        step_executions: Per-step results.
        started_at: When execution began.
        completed_at: When execution finished.
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_version: int = 1
    user_id: str = ""
    trigger_event: dict[str, Any] | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    step_executions: dict[str, StepExecution] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def get_step_result(self, step_id: str) -> dict[str, Any]:
        """Get the result of a completed step, or empty dict."""
        se = self.step_executions.get(step_id)
        if se and se.status == ExecutionStatus.COMPLETED:
            return se.result
        return {}


# ---------------------------------------------------------------------------
# Condition evaluation helpers
# ---------------------------------------------------------------------------


def resolve_field_path(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dot-notation path into a nested dict.

    Returns (found: bool, value: Any).
    """
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _evaluate_condition(condition: TriggerCondition, context: dict[str, Any]) -> bool:
    """Evaluate a single condition against a context dict."""
    found, actual = resolve_field_path(context, condition.field_path)

    if condition.operator == ConditionOperator.EXISTS:
        return found

    if not found:
        return False

    expected = condition.value
    op = condition.operator

    if op == ConditionOperator.EQ:
        return actual == expected
    if op == ConditionOperator.NEQ:
        return actual != expected
    if op == ConditionOperator.GT:
        return actual > expected
    if op == ConditionOperator.LT:
        return actual < expected
    if op == ConditionOperator.GTE:
        return actual >= expected
    if op == ConditionOperator.LTE:
        return actual <= expected
    if op == ConditionOperator.CONTAINS:
        return expected in actual if hasattr(actual, "__contains__") else False

    return False


def evaluate_conditions(
    conditions: list[TriggerCondition], context: dict[str, Any]
) -> bool:
    """Evaluate a list of conditions (AND logic). Empty list → True."""
    return all(_evaluate_condition(c, context) for c in conditions)

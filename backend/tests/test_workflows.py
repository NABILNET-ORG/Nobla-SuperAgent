"""Tests for Phase 6 workflow models, versioning, conditions, and triggers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nobla.automation.workflows.models import (
    ConditionBranch,
    ConditionConfig,
    ConditionOperator,
    ErrorHandling,
    ExecutionStatus,
    StepExecution,
    StepType,
    TriggerCondition,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
    evaluate_conditions,
    resolve_field_path,
)


# ---------------------------------------------------------------------------
# WorkflowStep tests
# ---------------------------------------------------------------------------


class TestWorkflowStep:
    """WorkflowStep dataclass."""

    def test_defaults(self):
        s = WorkflowStep()
        assert s.type == StepType.TOOL
        assert s.error_handling == ErrorHandling.FAIL
        assert s.max_retries == 0
        assert s.depends_on == []
        assert s.nl_source is None
        assert s.workflow_version == 1

    def test_custom_values(self):
        s = WorkflowStep(
            name="Run tests",
            type=StepType.TOOL,
            config={"tool": "code.run", "command": "pytest"},
            depends_on=["step-1"],
            error_handling=ErrorHandling.RETRY,
            max_retries=3,
            timeout_seconds=60,
            nl_source="run tests",
        )
        assert s.name == "Run tests"
        assert s.config["tool"] == "code.run"
        assert s.depends_on == ["step-1"]
        assert s.error_handling == ErrorHandling.RETRY
        assert s.max_retries == 3
        assert s.nl_source == "run tests"

    def test_unique_ids(self):
        ids = {WorkflowStep().step_id for _ in range(100)}
        assert len(ids) == 100

    def test_get_condition_config_non_condition_returns_none(self):
        s = WorkflowStep(type=StepType.TOOL)
        assert s.get_condition_config() is None

    def test_get_condition_config_parses_branches(self):
        s = WorkflowStep(
            type=StepType.CONDITION,
            config={
                "branches": [
                    {
                        "name": "pass",
                        "condition": {"field": "result.exit_code", "op": "eq", "value": 0},
                        "next_steps": ["deploy"],
                    },
                    {
                        "name": "fail",
                        "condition": {"field": "result.exit_code", "op": "neq", "value": 0},
                        "next_steps": ["notify"],
                    },
                ],
                "default_branch": "fail",
            },
        )
        cc = s.get_condition_config()
        assert cc is not None
        assert len(cc.branches) == 2
        assert cc.branches[0].name == "pass"
        assert cc.branches[0].condition.field_path == "result.exit_code"
        assert cc.branches[0].condition.operator == ConditionOperator.EQ
        assert cc.branches[0].next_steps == ["deploy"]
        assert cc.default_branch == "fail"


# ---------------------------------------------------------------------------
# WorkflowTrigger tests
# ---------------------------------------------------------------------------


class TestWorkflowTrigger:
    """WorkflowTrigger dataclass."""

    def test_defaults(self):
        t = WorkflowTrigger()
        assert t.event_pattern == "*"
        assert t.conditions == []
        assert t.active is True

    def test_with_conditions(self):
        t = WorkflowTrigger(
            event_pattern="webhook.github.*",
            conditions=[
                TriggerCondition(
                    field_path="payload.branch",
                    operator=ConditionOperator.EQ,
                    value="main",
                ),
            ],
        )
        assert t.event_pattern == "webhook.github.*"
        assert len(t.conditions) == 1
        assert t.conditions[0].field_path == "payload.branch"

    def test_unique_ids(self):
        ids = {WorkflowTrigger().trigger_id for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# Workflow versioning tests
# ---------------------------------------------------------------------------


class TestWorkflowVersioning:
    """Workflow versioning — bump, history, rollback queries."""

    def _make_workflow(self) -> Workflow:
        steps = [
            WorkflowStep(step_id="s1", name="step-1", workflow_version=1),
            WorkflowStep(step_id="s2", name="step-2", depends_on=["s1"], workflow_version=1),
        ]
        triggers = [
            WorkflowTrigger(event_pattern="webhook.github.*"),
        ]
        return Workflow(
            user_id="u1",
            name="CI Pipeline",
            steps=steps,
            triggers=triggers,
        )

    def test_initial_version(self):
        wf = self._make_workflow()
        assert wf.version == 1
        assert wf.list_versions() == [1]

    def test_bump_version_increments(self):
        wf = self._make_workflow()
        new_v = wf.bump_version()
        assert new_v == 2
        assert wf.version == 2

    def test_bump_preserves_old_version(self):
        wf = self._make_workflow()
        wf.bump_version()
        old = wf.get_version(1)
        assert old is not None
        old_steps, old_triggers = old
        assert len(old_steps) == 2
        assert old_steps[0].name == "step-1"

    def test_bump_with_new_steps(self):
        wf = self._make_workflow()
        new_steps = [
            WorkflowStep(step_id="s3", name="new-step"),
        ]
        wf.bump_version(new_steps=new_steps)
        assert len(wf.steps) == 1
        assert wf.steps[0].name == "new-step"
        assert wf.steps[0].workflow_version == 2

    def test_bump_with_new_triggers(self):
        wf = self._make_workflow()
        new_triggers = [
            WorkflowTrigger(event_pattern="manual.*"),
        ]
        wf.bump_version(new_triggers=new_triggers)
        assert len(wf.triggers) == 1
        assert wf.triggers[0].event_pattern == "manual.*"

    def test_multiple_bumps(self):
        wf = self._make_workflow()
        wf.bump_version()
        wf.bump_version()
        wf.bump_version()
        assert wf.version == 4
        assert wf.list_versions() == [1, 2, 3, 4]

    def test_get_current_version(self):
        wf = self._make_workflow()
        result = wf.get_version(1)
        assert result is not None
        steps, triggers = result
        assert len(steps) == 2

    def test_get_nonexistent_version_returns_none(self):
        wf = self._make_workflow()
        assert wf.get_version(99) is None

    def test_bump_updates_timestamp(self):
        wf = self._make_workflow()
        old_ts = wf.updated_at
        wf.bump_version()
        assert wf.updated_at >= old_ts

    def test_version_history_is_deep_copy(self):
        wf = self._make_workflow()
        wf.bump_version()
        # Mutating current steps should not affect v1 snapshot
        wf.steps[0].name = "mutated"
        old_steps, _ = wf.get_version(1)
        assert old_steps[0].name == "step-1"

    def test_bump_without_args_keeps_steps(self):
        wf = self._make_workflow()
        original_count = len(wf.steps)
        wf.bump_version()
        assert len(wf.steps) == original_count
        # But version number on steps is updated
        assert all(s.workflow_version == 2 for s in wf.steps)


# ---------------------------------------------------------------------------
# Condition evaluation tests
# ---------------------------------------------------------------------------


class TestConditionEvaluation:
    """TriggerCondition and ConditionConfig evaluation."""

    def test_eq(self):
        c = TriggerCondition(field_path="status", operator=ConditionOperator.EQ, value="ok")
        assert evaluate_conditions([c], {"status": "ok"}) is True
        assert evaluate_conditions([c], {"status": "fail"}) is False

    def test_neq(self):
        c = TriggerCondition(field_path="code", operator=ConditionOperator.NEQ, value=0)
        assert evaluate_conditions([c], {"code": 1}) is True
        assert evaluate_conditions([c], {"code": 0}) is False

    def test_gt(self):
        c = TriggerCondition(field_path="count", operator=ConditionOperator.GT, value=10)
        assert evaluate_conditions([c], {"count": 15}) is True
        assert evaluate_conditions([c], {"count": 5}) is False

    def test_lt(self):
        c = TriggerCondition(field_path="count", operator=ConditionOperator.LT, value=10)
        assert evaluate_conditions([c], {"count": 5}) is True
        assert evaluate_conditions([c], {"count": 15}) is False

    def test_gte(self):
        c = TriggerCondition(field_path="n", operator=ConditionOperator.GTE, value=10)
        assert evaluate_conditions([c], {"n": 10}) is True
        assert evaluate_conditions([c], {"n": 9}) is False

    def test_lte(self):
        c = TriggerCondition(field_path="n", operator=ConditionOperator.LTE, value=10)
        assert evaluate_conditions([c], {"n": 10}) is True
        assert evaluate_conditions([c], {"n": 11}) is False

    def test_contains(self):
        c = TriggerCondition(field_path="tags", operator=ConditionOperator.CONTAINS, value="urgent")
        assert evaluate_conditions([c], {"tags": ["urgent", "bug"]}) is True
        assert evaluate_conditions([c], {"tags": ["feature"]}) is False

    def test_contains_string(self):
        c = TriggerCondition(field_path="msg", operator=ConditionOperator.CONTAINS, value="error")
        assert evaluate_conditions([c], {"msg": "fatal error occurred"}) is True
        assert evaluate_conditions([c], {"msg": "all good"}) is False

    def test_exists(self):
        c = TriggerCondition(field_path="payload.data", operator=ConditionOperator.EXISTS)
        assert evaluate_conditions([c], {"payload": {"data": 42}}) is True
        assert evaluate_conditions([c], {"payload": {}}) is False

    def test_nested_field_path(self):
        c = TriggerCondition(
            field_path="payload.repo.branch",
            operator=ConditionOperator.EQ,
            value="main",
        )
        ctx = {"payload": {"repo": {"branch": "main"}}}
        assert evaluate_conditions([c], ctx) is True
        ctx2 = {"payload": {"repo": {"branch": "dev"}}}
        assert evaluate_conditions([c], ctx2) is False

    def test_missing_field_returns_false(self):
        c = TriggerCondition(field_path="nonexistent", operator=ConditionOperator.EQ, value=1)
        assert evaluate_conditions([c], {"other": 1}) is False

    def test_and_logic_multiple_conditions(self):
        c1 = TriggerCondition(field_path="a", operator=ConditionOperator.EQ, value=1)
        c2 = TriggerCondition(field_path="b", operator=ConditionOperator.EQ, value=2)
        assert evaluate_conditions([c1, c2], {"a": 1, "b": 2}) is True
        assert evaluate_conditions([c1, c2], {"a": 1, "b": 9}) is False

    def test_empty_conditions_returns_true(self):
        assert evaluate_conditions([], {"anything": True}) is True


class TestConditionConfig:
    """ConditionConfig — named branches with if/else logic."""

    def _make_config(self) -> ConditionConfig:
        return ConditionConfig(
            branches=[
                ConditionBranch(
                    name="passed",
                    condition=TriggerCondition(
                        field_path="exit_code", operator=ConditionOperator.EQ, value=0,
                    ),
                    next_steps=["deploy"],
                ),
                ConditionBranch(
                    name="failed",
                    condition=TriggerCondition(
                        field_path="exit_code", operator=ConditionOperator.NEQ, value=0,
                    ),
                    next_steps=["notify"],
                ),
            ],
            default_branch="failed",
        )

    def test_first_match_wins(self):
        cc = self._make_config()
        branch = cc.evaluate({"exit_code": 0})
        assert branch is not None
        assert branch.name == "passed"
        assert branch.next_steps == ["deploy"]

    def test_second_branch_match(self):
        cc = self._make_config()
        branch = cc.evaluate({"exit_code": 1})
        assert branch is not None
        assert branch.name == "failed"

    def test_default_branch_fallback(self):
        cc = ConditionConfig(
            branches=[
                ConditionBranch(
                    name="specific",
                    condition=TriggerCondition(
                        field_path="x", operator=ConditionOperator.EQ, value=42,
                    ),
                    next_steps=["a"],
                ),
                ConditionBranch(
                    name="default",
                    condition=TriggerCondition(
                        field_path="always_false", operator=ConditionOperator.EQ, value="never",
                    ),
                    next_steps=["b"],
                ),
            ],
            default_branch="default",
        )
        branch = cc.evaluate({"x": 99})
        assert branch is not None
        assert branch.name == "default"

    def test_no_match_no_default_returns_none(self):
        cc = ConditionConfig(
            branches=[
                ConditionBranch(
                    name="never",
                    condition=TriggerCondition(
                        field_path="x", operator=ConditionOperator.EQ, value=999,
                    ),
                    next_steps=["a"],
                ),
            ],
        )
        assert cc.evaluate({"x": 1}) is None


# ---------------------------------------------------------------------------
# resolve_field_path tests
# ---------------------------------------------------------------------------


class TestResolveFieldPath:
    """Dot-notation path resolution into nested dicts."""

    def test_simple(self):
        found, val = resolve_field_path({"a": 1}, "a")
        assert found is True
        assert val == 1

    def test_nested(self):
        found, val = resolve_field_path({"a": {"b": {"c": 3}}}, "a.b.c")
        assert found is True
        assert val == 3

    def test_missing(self):
        found, val = resolve_field_path({"a": 1}, "b")
        assert found is False
        assert val is None

    def test_partial_path(self):
        found, val = resolve_field_path({"a": {"b": 2}}, "a.c")
        assert found is False


# ---------------------------------------------------------------------------
# Execution model tests
# ---------------------------------------------------------------------------


class TestWorkflowExecution:
    """WorkflowExecution dataclass."""

    def test_defaults(self):
        ex = WorkflowExecution()
        assert ex.status == ExecutionStatus.PENDING
        assert ex.step_executions == {}
        assert ex.trigger_event is None

    def test_get_step_result_completed(self):
        ex = WorkflowExecution()
        se = StepExecution(
            step_id="s1", status=ExecutionStatus.COMPLETED,
            result={"output": "ok"},
        )
        ex.step_executions["s1"] = se
        assert ex.get_step_result("s1") == {"output": "ok"}

    def test_get_step_result_pending_returns_empty(self):
        ex = WorkflowExecution()
        se = StepExecution(step_id="s1", status=ExecutionStatus.PENDING)
        ex.step_executions["s1"] = se
        assert ex.get_step_result("s1") == {}

    def test_get_step_result_missing_returns_empty(self):
        ex = WorkflowExecution()
        assert ex.get_step_result("nonexistent") == {}


class TestStepExecution:
    """StepExecution dataclass."""

    def test_defaults(self):
        se = StepExecution()
        assert se.status == ExecutionStatus.PENDING
        assert se.result == {}
        assert se.error is None
        assert se.branch_taken is None

    def test_unique_ids(self):
        ids = {StepExecution().id for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestWorkflowEnums:
    """All workflow enums have expected values."""

    def test_workflow_status(self):
        assert WorkflowStatus.ACTIVE.value == "active"
        assert WorkflowStatus.PAUSED.value == "paused"
        assert WorkflowStatus.ARCHIVED.value == "archived"

    def test_step_type(self):
        assert StepType.TOOL.value == "tool"
        assert StepType.AGENT.value == "agent"
        assert StepType.CONDITION.value == "condition"
        assert StepType.WEBHOOK.value == "webhook"
        assert StepType.DELAY.value == "delay"
        assert StepType.APPROVAL.value == "approval"

    def test_error_handling(self):
        assert ErrorHandling.FAIL.value == "fail"
        assert ErrorHandling.RETRY.value == "retry"
        assert ErrorHandling.CONTINUE.value == "continue"
        assert ErrorHandling.SKIP.value == "skip"

    def test_execution_status(self):
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.PAUSED.value == "paused"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.SKIPPED.value == "skipped"

    def test_condition_operator(self):
        assert ConditionOperator.EQ.value == "eq"
        assert ConditionOperator.NEQ.value == "neq"
        assert ConditionOperator.GT.value == "gt"
        assert ConditionOperator.LT.value == "lt"
        assert ConditionOperator.GTE.value == "gte"
        assert ConditionOperator.LTE.value == "lte"
        assert ConditionOperator.CONTAINS.value == "contains"
        assert ConditionOperator.EXISTS.value == "exists"


# ---------------------------------------------------------------------------
# TriggerMatcher tests
# ---------------------------------------------------------------------------


class _FakeEventBus:
    """Event bus stub with subscribe/unsubscribe/fire."""

    def __init__(self):
        self.emitted: list = []
        self._handlers: dict[str, tuple] = {}
        self._next_id = 0

    async def emit(self, event):
        self.emitted.append(event)

    async def subscribe(self, pattern, handler):
        self._next_id += 1
        sub_id = str(self._next_id)
        self._handlers[sub_id] = (pattern, handler)
        return sub_id

    async def unsubscribe(self, sub_id):
        self._handlers.pop(sub_id, None)

    async def fire(self, event):
        import fnmatch as _fn
        for _, (pattern, handler) in self._handlers.items():
            if _fn.fnmatch(event.event_type, pattern):
                await handler(event)


def _make_event(event_type="webhook.github.push.received", **kwargs):
    from nobla.events.models import NoblaEvent
    defaults = dict(event_type=event_type, source="test", payload={})
    defaults.update(kwargs)
    return NoblaEvent(**defaults)


class TestTriggerMatcherRegistration:
    """Trigger registration and unregistration."""

    def setup_method(self):
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher
        self.bus = _FakeEventBus()
        self.matcher = TriggerMatcher(event_bus=self.bus)

    def test_register_trigger(self):
        t = WorkflowTrigger(event_pattern="webhook.github.*")
        self.matcher.register_trigger("wf-1", t)
        triggers = self.matcher.list_triggers()
        assert len(triggers) == 1
        assert triggers[0][0] == "wf-1"

    def test_unregister_trigger(self):
        t = WorkflowTrigger(event_pattern="webhook.github.*")
        self.matcher.register_trigger("wf-1", t)
        self.matcher.unregister_trigger(t.trigger_id)
        assert len(self.matcher.list_triggers()) == 0

    def test_register_workflow_triggers(self):
        triggers = [
            WorkflowTrigger(event_pattern="webhook.github.*"),
            WorkflowTrigger(event_pattern="scheduler.task.*"),
        ]
        self.matcher.register_workflow_triggers("wf-1", triggers)
        assert len(self.matcher.list_triggers()) == 2

    def test_unregister_workflow(self):
        triggers = [
            WorkflowTrigger(event_pattern="webhook.github.*"),
            WorkflowTrigger(event_pattern="scheduler.task.*"),
        ]
        self.matcher.register_workflow_triggers("wf-1", triggers)
        self.matcher.register_trigger("wf-2", WorkflowTrigger(event_pattern="*"))
        self.matcher.unregister_workflow("wf-1")
        remaining = self.matcher.list_triggers()
        assert len(remaining) == 1
        assert remaining[0][0] == "wf-2"


class TestTriggerMatcherLifecycle:
    """Start/stop subscription management."""

    def setup_method(self):
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher
        self.bus = _FakeEventBus()
        self.matcher = TriggerMatcher(event_bus=self.bus)

    @pytest.mark.asyncio
    async def test_start_subscribes(self):
        await self.matcher.start()
        assert len(self.bus._handlers) == 1

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self):
        await self.matcher.start()
        await self.matcher.stop()
        assert len(self.bus._handlers) == 0

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self):
        await self.matcher.stop()  # Should not raise


class TestTriggerMatcherMatching:
    """Event matching — patterns, conditions, callbacks."""

    def setup_method(self):
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher
        self.bus = _FakeEventBus()
        self.matcher = TriggerMatcher(event_bus=self.bus, dedup_window_seconds=0.5)
        self.fired: list[tuple] = []

        async def on_trigger(workflow_id, trigger, event):
            self.fired.append((workflow_id, trigger.trigger_id, event.event_type))

        self.matcher.set_callback(on_trigger)

    @pytest.mark.asyncio
    async def test_exact_pattern_match(self):
        t = WorkflowTrigger(event_pattern="webhook.github.push.received")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        assert len(self.fired) == 1
        assert self.fired[0][0] == "wf-1"

    @pytest.mark.asyncio
    async def test_wildcard_pattern_match(self):
        t = WorkflowTrigger(event_pattern="webhook.github.*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        assert len(self.fired) == 1

    @pytest.mark.asyncio
    async def test_no_match(self):
        t = WorkflowTrigger(event_pattern="webhook.stripe.*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        assert len(self.fired) == 0

    @pytest.mark.asyncio
    async def test_condition_pass(self):
        t = WorkflowTrigger(
            event_pattern="webhook.github.*",
            conditions=[
                TriggerCondition(
                    field_path="payload.branch",
                    operator=ConditionOperator.EQ,
                    value="main",
                ),
            ],
        )
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event(payload={"branch": "main"}))
        assert len(self.fired) == 1

    @pytest.mark.asyncio
    async def test_condition_fail(self):
        t = WorkflowTrigger(
            event_pattern="webhook.github.*",
            conditions=[
                TriggerCondition(
                    field_path="payload.branch",
                    operator=ConditionOperator.EQ,
                    value="main",
                ),
            ],
        )
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event(payload={"branch": "dev"}))
        assert len(self.fired) == 0

    @pytest.mark.asyncio
    async def test_multiple_conditions_and_logic(self):
        t = WorkflowTrigger(
            event_pattern="webhook.github.*",
            conditions=[
                TriggerCondition(field_path="payload.branch", operator=ConditionOperator.EQ, value="main"),
                TriggerCondition(field_path="payload.action", operator=ConditionOperator.EQ, value="push"),
            ],
        )
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        # Both match
        await self.bus.fire(_make_event(payload={"branch": "main", "action": "push"}))
        assert len(self.fired) == 1

        # One fails
        self.fired.clear()
        await self.bus.fire(_make_event(payload={"branch": "main", "action": "pr"}))
        assert len(self.fired) == 0

    @pytest.mark.asyncio
    async def test_multiple_triggers_or_logic(self):
        """Multiple triggers on same workflow — any match fires."""
        t1 = WorkflowTrigger(event_pattern="webhook.github.*")
        t2 = WorkflowTrigger(event_pattern="webhook.gitlab.*")
        self.matcher.register_trigger("wf-1", t1)
        self.matcher.register_trigger("wf-1", t2)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        assert len(self.fired) == 1

        await self.bus.fire(_make_event("webhook.gitlab.push.received"))
        assert len(self.fired) == 2

    @pytest.mark.asyncio
    async def test_inactive_trigger_skipped(self):
        t = WorkflowTrigger(event_pattern="webhook.github.*", active=False)
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        assert len(self.fired) == 0

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash(self):
        async def bad_callback(wf_id, trigger, event):
            raise RuntimeError("boom")

        self.matcher.set_callback(bad_callback)
        t = WorkflowTrigger(event_pattern="*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        # Should not raise
        await self.bus.fire(_make_event())

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        t = WorkflowTrigger(event_pattern="webhook.github.*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event("webhook.github.push.received"))
        await self.bus.fire(_make_event("webhook.stripe.payment.received"))

        assert self.matcher.events_received == 2
        assert self.matcher.events_matched == 1


class TestTriggerMatcherDedup:
    """Deduplication — same trigger+correlation_id within window is dropped."""

    def setup_method(self):
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher
        self.bus = _FakeEventBus()
        self.matcher = TriggerMatcher(event_bus=self.bus, dedup_window_seconds=1.0)
        self.fired: list[tuple] = []

        async def on_trigger(workflow_id, trigger, event):
            self.fired.append((workflow_id, trigger.trigger_id, event.correlation_id))

        self.matcher.set_callback(on_trigger)

    @pytest.mark.asyncio
    async def test_duplicate_within_window_dropped(self):
        t = WorkflowTrigger(event_pattern="*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        event = _make_event()
        await self.bus.fire(event)
        await self.bus.fire(event)  # Same correlation_id

        assert len(self.fired) == 1
        assert self.matcher.events_deduplicated == 1

    @pytest.mark.asyncio
    async def test_different_correlation_ids_not_deduped(self):
        t = WorkflowTrigger(event_pattern="*")
        self.matcher.register_trigger("wf-1", t)
        await self.matcher.start()

        await self.bus.fire(_make_event())
        await self.bus.fire(_make_event())  # Different uuid each time

        assert len(self.fired) == 2
        assert self.matcher.events_deduplicated == 0

    @pytest.mark.asyncio
    async def test_dedup_expires_after_window(self):
        import time
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher

        # Tiny window
        matcher = TriggerMatcher(event_bus=self.bus, dedup_window_seconds=0.05)
        matcher.set_callback(
            lambda wf, t, e: self.fired.append((wf, t.trigger_id, e.correlation_id))
        )
        t = WorkflowTrigger(event_pattern="*")
        matcher.register_trigger("wf-1", t)
        await matcher.start()

        event = _make_event()
        await self.bus.fire(event)
        assert len(self.fired) == 1

        # Wait for dedup window to expire
        time.sleep(0.06)

        await self.bus.fire(event)
        assert len(self.fired) == 2  # No longer deduplicated

    @pytest.mark.asyncio
    async def test_dedup_per_trigger(self):
        """Different triggers with same event should both fire."""
        t1 = WorkflowTrigger(event_pattern="*")
        t2 = WorkflowTrigger(event_pattern="*")
        self.matcher.register_trigger("wf-1", t1)
        self.matcher.register_trigger("wf-2", t2)
        await self.matcher.start()

        event = _make_event()
        await self.bus.fire(event)

        # Both triggers fire since they have different trigger_ids
        assert len(self.fired) == 2


class TestTriggerMatcherContextBuilding:
    """Context dict built from events for condition evaluation."""

    def test_build_context(self):
        from nobla.automation.workflows.trigger_matcher import TriggerMatcher
        bus = _FakeEventBus()
        matcher = TriggerMatcher(event_bus=bus)

        event = _make_event(
            payload={"branch": "main", "action": "push"},
            user_id="u1",
        )
        ctx = matcher._build_context(event)

        assert ctx["event_type"] == "webhook.github.push.received"
        assert ctx["source"] == "test"
        assert ctx["user_id"] == "u1"
        assert ctx["payload"]["branch"] == "main"
        # Flattened payload fields
        assert ctx["branch"] == "main"
        assert ctx["action"] == "push"


# ---------------------------------------------------------------------------
# Topological sort tests
# ---------------------------------------------------------------------------


class TestTopologicalSortSteps:
    """topological_sort_steps — Kahn's algorithm for WorkflowStep."""

    def test_empty(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        assert topological_sort_steps([]) == []

    def test_single_step(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        s = WorkflowStep(step_id="s1")
        tiers = topological_sort_steps([s])
        assert len(tiers) == 1
        assert tiers[0][0].step_id == "s1"

    def test_independent_steps_single_tier(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        steps = [
            WorkflowStep(step_id="s1"),
            WorkflowStep(step_id="s2"),
            WorkflowStep(step_id="s3"),
        ]
        tiers = topological_sort_steps(steps)
        assert len(tiers) == 1
        assert len(tiers[0]) == 3

    def test_linear_chain(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        steps = [
            WorkflowStep(step_id="s1"),
            WorkflowStep(step_id="s2", depends_on=["s1"]),
            WorkflowStep(step_id="s3", depends_on=["s2"]),
        ]
        tiers = topological_sort_steps(steps)
        assert len(tiers) == 3
        assert tiers[0][0].step_id == "s1"
        assert tiers[1][0].step_id == "s2"
        assert tiers[2][0].step_id == "s3"

    def test_diamond_dependency(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        steps = [
            WorkflowStep(step_id="s1"),
            WorkflowStep(step_id="s2", depends_on=["s1"]),
            WorkflowStep(step_id="s3", depends_on=["s1"]),
            WorkflowStep(step_id="s4", depends_on=["s2", "s3"]),
        ]
        tiers = topological_sort_steps(steps)
        assert len(tiers) == 3
        tier_ids = [[s.step_id for s in t] for t in tiers]
        assert tier_ids[0] == ["s1"]
        assert set(tier_ids[1]) == {"s2", "s3"}
        assert tier_ids[2] == ["s4"]

    def test_cycle_raises(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        steps = [
            WorkflowStep(step_id="s1", depends_on=["s2"]),
            WorkflowStep(step_id="s2", depends_on=["s1"]),
        ]
        with pytest.raises(ValueError, match="Cycle"):
            topological_sort_steps(steps)

    def test_missing_dependency_raises(self):
        from nobla.automation.workflows.executor import topological_sort_steps
        steps = [
            WorkflowStep(step_id="s1", depends_on=["nonexistent"]),
        ]
        with pytest.raises(ValueError, match="unknown steps"):
            topological_sort_steps(steps)


# ---------------------------------------------------------------------------
# WorkflowExecutor tests
# ---------------------------------------------------------------------------


class _FakeEventBus2:
    """Event bus stub for executor tests."""

    def __init__(self):
        self.emitted: list = []

    async def emit(self, event):
        self.emitted.append(event)


class TestWorkflowExecutorBasic:
    """WorkflowExecutor — basic execution flows."""

    def setup_method(self):
        from nobla.automation.workflows.executor import WorkflowExecutor
        self.bus = _FakeEventBus2()
        self.tool_calls: list[dict] = []

        async def tool_cb(config, user_id):
            self.tool_calls.append(config)
            return {"output": config.get("tool", "done"), "exit_code": 0}

        self.executor = WorkflowExecutor(
            event_bus=self.bus,
            tool_callback=tool_cb,
        )

    def _make_workflow(self, steps) -> Workflow:
        return Workflow(
            user_id="u1", name="test-wf", steps=steps,
        )

    def _make_execution(self, wf) -> WorkflowExecution:
        return WorkflowExecution(
            workflow_id=wf.workflow_id, user_id=wf.user_id,
        )

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        wf = self._make_workflow([])
        ex = self._make_execution(wf)
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_single_tool_step(self):
        steps = [WorkflowStep(step_id="s1", name="run", type=StepType.TOOL, config={"tool": "code.run"})]
        wf = self._make_workflow(steps)
        ex = self._make_execution(wf)
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert len(self.tool_calls) == 1
        se = result.step_executions["s1"]
        assert se.status == ExecutionStatus.COMPLETED
        assert se.result["output"] == "code.run"

    @pytest.mark.asyncio
    async def test_parallel_steps(self):
        steps = [
            WorkflowStep(step_id="s1", type=StepType.TOOL, config={"tool": "a"}),
            WorkflowStep(step_id="s2", type=StepType.TOOL, config={"tool": "b"}),
        ]
        wf = self._make_workflow(steps)
        ex = self._make_execution(wf)
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert len(self.tool_calls) == 2

    @pytest.mark.asyncio
    async def test_sequential_dependency(self):
        steps = [
            WorkflowStep(step_id="s1", type=StepType.TOOL, config={"tool": "first"}),
            WorkflowStep(step_id="s2", type=StepType.TOOL, config={"tool": "second"}, depends_on=["s1"]),
        ]
        wf = self._make_workflow(steps)
        ex = self._make_execution(wf)
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert self.tool_calls[0]["tool"] == "first"
        assert self.tool_calls[1]["tool"] == "second"

    @pytest.mark.asyncio
    async def test_emits_lifecycle_events(self):
        steps = [WorkflowStep(step_id="s1", type=StepType.TOOL, config={})]
        wf = self._make_workflow(steps)
        ex = self._make_execution(wf)
        await self.executor.execute(wf, ex)
        event_types = [e.event_type for e in self.bus.emitted]
        assert "workflow.execution.started" in event_types
        assert "workflow.step.started" in event_types
        assert "workflow.step.completed" in event_types
        assert "workflow.execution.completed" in event_types


class TestWorkflowExecutorErrorHandling:
    """Error handling — fail, retry, continue, skip."""

    def setup_method(self):
        from nobla.automation.workflows.executor import WorkflowExecutor
        self.bus = _FakeEventBus2()
        self.call_count = 0

        async def failing_tool(config, user_id):
            self.call_count += 1
            if config.get("fail", False):
                raise RuntimeError("tool failed")
            return {"ok": True}

        self.executor = WorkflowExecutor(
            event_bus=self.bus,
            tool_callback=failing_tool,
        )

    @pytest.mark.asyncio
    async def test_fail_cascades_to_dependents(self):
        steps = [
            WorkflowStep(step_id="s1", type=StepType.TOOL, config={"fail": True}),
            WorkflowStep(step_id="s2", type=StepType.TOOL, config={}, depends_on=["s1"]),
        ]
        wf = Workflow(user_id="u1", name="fail-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.FAILED
        assert result.step_executions["s1"].status == ExecutionStatus.FAILED
        assert result.step_executions["s2"].status == ExecutionStatus.FAILED
        assert "cascade" in result.step_executions["s2"].error.lower()

    @pytest.mark.asyncio
    async def test_retry_attempts(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.TOOL, config={"fail": True},
                error_handling=ErrorHandling.RETRY, max_retries=2,
            ),
        ]
        wf = Workflow(user_id="u1", name="retry-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.step_executions["s1"].status == ExecutionStatus.FAILED
        assert self.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_continue_allows_dependents(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.TOOL, config={"fail": True},
                error_handling=ErrorHandling.CONTINUE,
            ),
            WorkflowStep(step_id="s2", type=StepType.TOOL, config={}, depends_on=["s1"]),
        ]
        wf = Workflow(user_id="u1", name="continue-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        # s1 failed but s2 still ran
        assert result.step_executions["s1"].status == ExecutionStatus.FAILED
        assert result.step_executions["s2"].status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_skip_marks_step_skipped(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.TOOL, config={"fail": True},
                error_handling=ErrorHandling.SKIP,
            ),
        ]
        wf = Workflow(user_id="u1", name="skip-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.step_executions["s1"].status == ExecutionStatus.SKIPPED


class TestWorkflowExecutorStepTypes:
    """Step type dispatch — delay, webhook, condition, approval."""

    def setup_method(self):
        from nobla.automation.workflows.executor import WorkflowExecutor
        self.bus = _FakeEventBus2()
        self.webhook_calls: list = []
        self.approval_result = True

        async def webhook_cb(url, payload, headers):
            self.webhook_calls.append(url)
            return {"status_code": 200}

        async def approval_cb(user_id, message, config):
            return self.approval_result

        async def tool_cb(config, user_id):
            return {"exit_code": config.get("exit_code", 0)}

        self.executor = WorkflowExecutor(
            event_bus=self.bus,
            tool_callback=tool_cb,
            webhook_callback=webhook_cb,
            approval_callback=approval_cb,
        )

    @pytest.mark.asyncio
    async def test_delay_step(self):
        steps = [
            WorkflowStep(step_id="s1", type=StepType.DELAY, config={"seconds": 0.01}),
        ]
        wf = Workflow(user_id="u1", name="delay-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert result.step_executions["s1"].result["delayed_seconds"] == 0.01

    @pytest.mark.asyncio
    async def test_webhook_step(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.WEBHOOK,
                config={"url": "https://example.com/hook", "payload": {"key": "val"}},
            ),
        ]
        wf = Workflow(user_id="u1", name="webhook-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert len(self.webhook_calls) == 1
        assert self.webhook_calls[0] == "https://example.com/hook"

    @pytest.mark.asyncio
    async def test_approval_step_approved(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.APPROVAL,
                config={"message": "Deploy?"},
            ),
        ]
        wf = Workflow(user_id="u1", name="approval-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert result.step_executions["s1"].result["approved"] is True

    @pytest.mark.asyncio
    async def test_approval_step_denied(self):
        self.approval_result = False
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.APPROVAL,
                config={"message": "Deploy?"},
            ),
        ]
        wf = Workflow(user_id="u1", name="approval-deny", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.step_executions["s1"].status == ExecutionStatus.FAILED
        assert "denied" in result.step_executions["s1"].error.lower()


class TestWorkflowExecutorConditionBranches:
    """Condition step evaluation and branch-based step enabling."""

    def setup_method(self):
        from nobla.automation.workflows.executor import WorkflowExecutor
        self.bus = _FakeEventBus2()
        self.tool_calls: list = []

        async def tool_cb(config, user_id):
            self.tool_calls.append(config.get("name", ""))
            return {"exit_code": config.get("exit_code", 0)}

        self.executor = WorkflowExecutor(
            event_bus=self.bus,
            tool_callback=tool_cb,
        )

    @pytest.mark.asyncio
    async def test_condition_takes_first_branch(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.TOOL,
                config={"name": "test", "exit_code": 0},
            ),
            WorkflowStep(
                step_id="s2", type=StepType.CONDITION,
                depends_on=["s1"],
                config={
                    "branches": [
                        {
                            "name": "pass",
                            "condition": {"field": "exit_code", "op": "eq", "value": 0},
                            "next_steps": ["s3"],
                        },
                        {
                            "name": "fail",
                            "condition": {"field": "exit_code", "op": "neq", "value": 0},
                            "next_steps": ["s4"],
                        },
                    ],
                    "default_branch": "fail",
                },
            ),
            WorkflowStep(
                step_id="s3", type=StepType.TOOL, depends_on=["s2"],
                config={"name": "deploy"},
            ),
            WorkflowStep(
                step_id="s4", type=StepType.TOOL, depends_on=["s2"],
                config={"name": "notify_failure"},
            ),
        ]
        wf = Workflow(user_id="u1", name="branch-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)

        assert result.status == ExecutionStatus.COMPLETED
        # s3 (deploy) ran, s4 (notify_failure) was skipped
        assert result.step_executions["s3"].status == ExecutionStatus.COMPLETED
        assert result.step_executions["s4"].status == ExecutionStatus.SKIPPED
        assert "deploy" in self.tool_calls
        assert "notify_failure" not in self.tool_calls

    @pytest.mark.asyncio
    async def test_condition_branch_taken_recorded(self):
        steps = [
            WorkflowStep(
                step_id="s1", type=StepType.CONDITION,
                config={
                    "branches": [
                        {
                            "name": "always",
                            "condition": {"field": "nonexistent", "op": "exists"},
                            "next_steps": [],
                        },
                    ],
                    "default_branch": "always",
                },
            ),
        ]
        wf = Workflow(user_id="u1", name="branch-record", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.step_executions["s1"].branch_taken == "always"

    @pytest.mark.asyncio
    async def test_complex_dag_three_tiers(self):
        """s1 parallel s2 → s3 depends on both → s4 depends on s3."""
        steps = [
            WorkflowStep(step_id="s1", type=StepType.TOOL, config={"name": "a"}),
            WorkflowStep(step_id="s2", type=StepType.TOOL, config={"name": "b"}),
            WorkflowStep(step_id="s3", type=StepType.TOOL, config={"name": "c"}, depends_on=["s1", "s2"]),
            WorkflowStep(step_id="s4", type=StepType.TOOL, config={"name": "d"}, depends_on=["s3"]),
        ]
        wf = Workflow(user_id="u1", name="complex-dag", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.status == ExecutionStatus.COMPLETED
        assert len(self.tool_calls) == 4
        # c must come after a and b; d must come after c
        c_idx = self.tool_calls.index("c")
        d_idx = self.tool_calls.index("d")
        assert c_idx < d_idx

    @pytest.mark.asyncio
    async def test_no_callback_raises_for_tool(self):
        from nobla.automation.workflows.executor import WorkflowExecutor
        executor = WorkflowExecutor(event_bus=self.bus)
        steps = [WorkflowStep(step_id="s1", type=StepType.TOOL, config={})]
        wf = Workflow(user_id="u1", name="no-cb", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await executor.execute(wf, ex)
        assert result.step_executions["s1"].status == ExecutionStatus.FAILED
        assert "callback" in result.step_executions["s1"].error.lower()

    @pytest.mark.asyncio
    async def test_execution_timestamps(self):
        steps = [WorkflowStep(step_id="s1", type=StepType.TOOL, config={"name": "x"})]
        wf = Workflow(user_id="u1", name="ts-test", steps=steps)
        ex = WorkflowExecution(workflow_id=wf.workflow_id, user_id="u1")
        result = await self.executor.execute(wf, ex)
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at
        se = result.step_executions["s1"]
        assert se.started_at is not None
        assert se.completed_at is not None


# ---------------------------------------------------------------------------
# WorkflowInterpreter tests
# ---------------------------------------------------------------------------


class TestWorkflowInterpreterHeuristic:
    """Heuristic (no-LLM) NL parsing."""

    def setup_method(self):
        from nobla.automation.workflows.interpreter import WorkflowInterpreter
        self.interp = WorkflowInterpreter(router=None)

    @pytest.mark.asyncio
    async def test_simple_workflow(self):
        wf = await self.interp.interpret(
            "run tests then deploy to staging",
            user_id="u1",
        )
        assert wf.user_id == "u1"
        assert len(wf.steps) >= 2
        assert wf.steps[0].nl_source is not None

    @pytest.mark.asyncio
    async def test_github_trigger_detected(self):
        wf = await self.interp.interpret(
            "When GitHub pushes, run tests then deploy",
            user_id="u1",
        )
        assert len(wf.triggers) == 1
        assert "github" in wf.triggers[0].event_pattern

    @pytest.mark.asyncio
    async def test_branch_condition_extracted(self):
        wf = await self.interp.interpret(
            "When GitHub pushes to branch main, run tests",
            user_id="u1",
        )
        trigger = wf.triggers[0]
        assert len(trigger.conditions) == 1
        assert trigger.conditions[0].field_path == "payload.branch"
        assert trigger.conditions[0].value == "main"

    @pytest.mark.asyncio
    async def test_time_trigger_detected(self):
        wf = await self.interp.interpret(
            "Every Monday at 9am, generate a report",
            user_id="u1",
        )
        assert "scheduler.cron" in wf.triggers[0].event_pattern

    @pytest.mark.asyncio
    async def test_manual_trigger_fallback(self):
        wf = await self.interp.interpret(
            "generate a report and send it to the team",
            user_id="u1",
        )
        assert "manual" in wf.triggers[0].event_pattern

    @pytest.mark.asyncio
    async def test_notify_step_type(self):
        wf = await self.interp.interpret(
            "notify the team on Slack",
            user_id="u1",
        )
        webhook_steps = [s for s in wf.steps if s.type == StepType.WEBHOOK]
        assert len(webhook_steps) >= 1

    @pytest.mark.asyncio
    async def test_delay_step_with_duration(self):
        wf = await self.interp.interpret(
            "wait 5 minutes then send notification",
            user_id="u1",
        )
        delay_steps = [s for s in wf.steps if s.type == StepType.DELAY]
        assert len(delay_steps) >= 1
        assert delay_steps[0].config["seconds"] == 300

    @pytest.mark.asyncio
    async def test_approval_step(self):
        wf = await self.interp.interpret(
            "approve the deployment",
            user_id="u1",
        )
        approval_steps = [s for s in wf.steps if s.type == StepType.APPROVAL]
        assert len(approval_steps) >= 1

    @pytest.mark.asyncio
    async def test_sequential_dependencies(self):
        wf = await self.interp.interpret(
            "run tests, then deploy, then notify team",
            user_id="u1",
        )
        # Each step should depend on the previous
        for i in range(1, len(wf.steps)):
            assert wf.steps[i].depends_on == [wf.steps[i - 1].step_id]

    @pytest.mark.asyncio
    async def test_custom_name(self):
        wf = await self.interp.interpret(
            "run tests", user_id="u1", name="CI Pipeline",
        )
        assert wf.name == "CI Pipeline"

    @pytest.mark.asyncio
    async def test_auto_generated_name(self):
        wf = await self.interp.interpret(
            "a very long workflow description that has many words in it",
            user_id="u1",
        )
        assert "..." in wf.name
        assert len(wf.name) < 60

    @pytest.mark.asyncio
    async def test_nl_source_on_every_step(self):
        wf = await self.interp.interpret(
            "run tests then deploy then notify",
            user_id="u1",
        )
        for step in wf.steps:
            assert step.nl_source is not None
            assert len(step.nl_source) > 0


class TestWorkflowInterpreterLLMParsing:
    """LLM JSON response parsing (without actual LLM call)."""

    def setup_method(self):
        from nobla.automation.workflows.interpreter import WorkflowInterpreter
        self.interp = WorkflowInterpreter(router=None)

    def test_parse_llm_response_basic(self):
        data = {
            "triggers": [
                {"event_pattern": "webhook.github.push.*", "conditions": []}
            ],
            "steps": [
                {"id": "s1", "name": "Run tests", "type": "tool",
                 "config": {"tool": "code.run"}, "depends_on": [],
                 "nl_source": "run tests"},
                {"id": "s2", "name": "Deploy", "type": "tool",
                 "config": {"tool": "ssh.exec"}, "depends_on": ["s1"],
                 "nl_source": "deploy"},
            ],
        }
        wf = self.interp._parse_llm_response(data, "test desc", "u1", "Test WF")
        assert wf.name == "Test WF"
        assert len(wf.triggers) == 1
        assert len(wf.steps) == 2
        assert wf.steps[0].nl_source == "run tests"
        # s2 depends on s1 (resolved UUID)
        assert wf.steps[1].depends_on == [wf.steps[0].step_id]

    def test_parse_llm_response_with_conditions(self):
        data = {
            "triggers": [
                {
                    "event_pattern": "webhook.github.*",
                    "conditions": [
                        {"field": "payload.branch", "op": "eq", "value": "main"},
                    ],
                }
            ],
            "steps": [],
        }
        wf = self.interp._parse_llm_response(data, "desc", "u1", "WF")
        assert len(wf.triggers[0].conditions) == 1
        assert wf.triggers[0].conditions[0].operator == ConditionOperator.EQ

    def test_parse_llm_response_condition_step_refs_resolved(self):
        data = {
            "triggers": [{"event_pattern": "manual.*"}],
            "steps": [
                {"id": "s1", "name": "Test", "type": "tool", "config": {},
                 "depends_on": []},
                {"id": "s2", "name": "Check", "type": "condition",
                 "config": {
                     "branches": [
                         {"name": "pass", "condition": {"field": "x", "op": "eq", "value": 0},
                          "next_steps": ["s3"]},
                     ],
                     "default_branch": "pass",
                 },
                 "depends_on": ["s1"]},
                {"id": "s3", "name": "Deploy", "type": "tool", "config": {},
                 "depends_on": ["s2"]},
            ],
        }
        wf = self.interp._parse_llm_response(data, "desc", "u1", "WF")
        # s3 next_steps reference should be resolved to UUID
        cond_step = wf.steps[1]
        branch_next = cond_step.config["branches"][0]["next_steps"]
        assert branch_next == [wf.steps[2].step_id]

    def test_parse_llm_response_default_trigger(self):
        """No triggers in LLM response → manual trigger added."""
        data = {"triggers": [], "steps": [
            {"id": "s1", "name": "Do thing", "type": "tool", "config": {},
             "depends_on": []},
        ]}
        wf = self.interp._parse_llm_response(data, "desc", "u1", "WF")
        assert len(wf.triggers) == 1
        assert wf.triggers[0].event_pattern == "manual.*"

    def test_parse_llm_response_unknown_step_type_defaults_to_tool(self):
        data = {"triggers": [], "steps": [
            {"id": "s1", "name": "X", "type": "unknown_type", "config": {},
             "depends_on": []},
        ]}
        wf = self.interp._parse_llm_response(data, "desc", "u1", "WF")
        assert wf.steps[0].type == StepType.TOOL

    def test_parse_llm_response_unknown_dep_skipped(self):
        data = {"triggers": [], "steps": [
            {"id": "s1", "name": "A", "type": "tool", "config": {},
             "depends_on": ["nonexistent"]},
        ]}
        wf = self.interp._parse_llm_response(data, "desc", "u1", "WF")
        assert wf.steps[0].depends_on == []


class TestWorkflowInterpreterHelpers:
    """Helper methods — clause splitting, name generation."""

    def setup_method(self):
        from nobla.automation.workflows.interpreter import WorkflowInterpreter
        self.interp = WorkflowInterpreter(router=None)

    def test_split_clauses_then(self):
        clauses = self.interp._split_clauses("run tests then deploy then notify")
        assert len(clauses) == 3

    def test_split_clauses_comma(self):
        clauses = self.interp._split_clauses("run tests, deploy, notify")
        assert len(clauses) == 3

    def test_split_clauses_and_then(self):
        clauses = self.interp._split_clauses("build and then test and then deploy")
        assert len(clauses) == 3

    def test_generate_name_short(self):
        assert self.interp._generate_name("deploy to prod") == "deploy to prod"

    def test_generate_name_long(self):
        name = self.interp._generate_name("a very long description with many words that goes on")
        assert "..." in name

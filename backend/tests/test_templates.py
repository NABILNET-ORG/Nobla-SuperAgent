"""Tests for Phase 6 Workflow Templates + Import/Export."""

from __future__ import annotations

import json

import pytest

from nobla.automation.workflows.models import (
    ConditionOperator,
    ErrorHandling,
    StepType,
    TriggerCondition,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
)
from nobla.automation.workflows.templates import (
    SCHEMA_VERSION,
    TemplateCategory,
    TemplateStep,
    TemplateTrigger,
    WorkflowExportData,
    WorkflowTemplate,
    workflow_step_to_template_step,
    workflow_trigger_to_template_trigger,
)
from nobla.automation.workflows.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Stubs (shared with test_workflows_service.py)
# ---------------------------------------------------------------------------


class _FakeEventBus:
    def __init__(self):
        self.emitted = []
        self._handlers = {}
        self._next = 0

    async def emit(self, event):
        self.emitted.append(event)

    async def subscribe(self, pattern, handler):
        self._next += 1
        sid = str(self._next)
        self._handlers[sid] = (pattern, handler)
        return sid

    async def unsubscribe(self, sid):
        self._handlers.pop(sid, None)


def _make_service(bus=None):
    from nobla.automation.workflows.executor import WorkflowExecutor
    from nobla.automation.workflows.interpreter import WorkflowInterpreter
    from nobla.automation.workflows.trigger_matcher import TriggerMatcher
    from nobla.automation.workflows.service import WorkflowService

    bus = bus or _FakeEventBus()

    async def tool_cb(config, user_id):
        return {"output": "ok", "exit_code": 0}

    executor = WorkflowExecutor(event_bus=bus, tool_callback=tool_cb)
    interpreter = WorkflowInterpreter(router=None)
    matcher = TriggerMatcher(event_bus=bus)
    return WorkflowService(
        executor=executor,
        interpreter=interpreter,
        trigger_matcher=matcher,
        event_bus=bus,
    ), bus


def _make_workflow(**kwargs) -> Workflow:
    defaults = dict(
        user_id="u1",
        name="Test WF",
        description="A test workflow",
        steps=[
            WorkflowStep(
                step_id="s1", name="Fetch Data",
                type=StepType.TOOL, config={"tool": "fetch"},
            ),
            WorkflowStep(
                step_id="s2", name="Check Result",
                type=StepType.CONDITION, depends_on=["s1"],
                config={"branches": []},
            ),
        ],
        triggers=[
            WorkflowTrigger(
                event_pattern="webhook.github.*",
                conditions=[
                    TriggerCondition(
                        field_path="action",
                        operator=ConditionOperator.EQ,
                        value="push",
                    ),
                ],
            ),
        ],
    )
    defaults.update(kwargs)
    return Workflow(**defaults)


# ===========================================================================
# TemplateStep tests
# ===========================================================================


class TestTemplateStep:

    def test_to_dict_basic(self):
        s = TemplateStep(ref_id="s1", name="Build", type="tool", config={"tool": "build"})
        d = s.to_dict()
        assert d["ref_id"] == "s1"
        assert d["name"] == "Build"
        assert d["type"] == "tool"
        assert "timeout_seconds" not in d  # None omitted

    def test_to_dict_with_optional_fields(self):
        s = TemplateStep(ref_id="s1", name="Build", timeout_seconds=30, description="Builds things")
        d = s.to_dict()
        assert d["timeout_seconds"] == 30
        assert d["description"] == "Builds things"

    def test_from_dict(self):
        d = {"ref_id": "x", "name": "X", "type": "agent", "depends_on": ["y"], "max_retries": 3}
        s = TemplateStep.from_dict(d)
        assert s.ref_id == "x"
        assert s.type == "agent"
        assert s.depends_on == ["y"]
        assert s.max_retries == 3

    def test_from_dict_defaults(self):
        s = TemplateStep.from_dict({})
        assert s.ref_id == ""
        assert s.type == "tool"
        assert s.error_handling == "fail"

    def test_round_trip(self):
        s = TemplateStep(ref_id="r", name="R", type="delay", config={"secs": 5}, depends_on=["a", "b"])
        s2 = TemplateStep.from_dict(s.to_dict())
        assert s2.ref_id == s.ref_id
        assert s2.config == s.config
        assert s2.depends_on == s.depends_on


# ===========================================================================
# TemplateTrigger tests
# ===========================================================================


class TestTemplateTrigger:

    def test_to_dict(self):
        t = TemplateTrigger(event_pattern="webhook.*", conditions=[{"field_path": "a", "operator": "eq", "value": 1}])
        d = t.to_dict()
        assert d["event_pattern"] == "webhook.*"
        assert len(d["conditions"]) == 1

    def test_from_dict(self):
        t = TemplateTrigger.from_dict({"event_pattern": "schedule.daily", "description": "Daily"})
        assert t.event_pattern == "schedule.daily"
        assert t.description == "Daily"

    def test_round_trip(self):
        t = TemplateTrigger(event_pattern="test.*", conditions=[{"f": "v"}], description="Test")
        t2 = TemplateTrigger.from_dict(t.to_dict())
        assert t2.event_pattern == t.event_pattern
        assert t2.conditions == t.conditions


# ===========================================================================
# WorkflowTemplate tests
# ===========================================================================


class TestWorkflowTemplate:

    def test_to_dict(self):
        t = WorkflowTemplate(name="T1", category=TemplateCategory.CI_CD, tags=["ci"])
        d = t.to_dict()
        assert d["name"] == "T1"
        assert d["category"] == "ci_cd"
        assert d["tags"] == ["ci"]
        assert "created_at" in d

    def test_from_dict(self):
        d = {
            "name": "T2", "category": "devops", "tags": ["ops"],
            "author": "me", "version": "2.0.0",
            "steps": [{"ref_id": "s1", "name": "S1"}],
            "triggers": [{"event_pattern": "manual.*"}],
        }
        t = WorkflowTemplate.from_dict(d)
        assert t.name == "T2"
        assert t.category == TemplateCategory.DEVOPS
        assert len(t.steps) == 1
        assert len(t.triggers) == 1

    def test_round_trip(self):
        t = WorkflowTemplate(
            name="RT", category=TemplateCategory.DATA_PIPELINE,
            steps=[TemplateStep(ref_id="a", name="A")],
            triggers=[TemplateTrigger(event_pattern="schedule.*")],
        )
        t2 = WorkflowTemplate.from_dict(t.to_dict())
        assert t2.name == t.name
        assert t2.category == t.category
        assert len(t2.steps) == 1
        assert len(t2.triggers) == 1

    def test_defaults(self):
        t = WorkflowTemplate()
        assert t.category == TemplateCategory.CUSTOM
        assert t.bundled is False
        assert t.version == "1.0.0"


# ===========================================================================
# WorkflowExportData tests
# ===========================================================================


class TestWorkflowExportData:

    def test_to_dict_has_schema_version(self):
        e = WorkflowExportData(name="E1")
        d = e.to_dict()
        assert d["$nobla_version"] == SCHEMA_VERSION
        assert d["workflow"]["name"] == "E1"

    def test_to_json(self):
        e = WorkflowExportData(name="E1")
        j = e.to_json()
        parsed = json.loads(j)
        assert parsed["$nobla_version"] == SCHEMA_VERSION

    def test_from_dict_valid(self):
        d = {
            "$nobla_version": "1.0",
            "workflow": {"name": "Imported", "steps": [], "triggers": []},
            "source": {"workflow_id": "abc", "workflow_version": 3},
        }
        e = WorkflowExportData.from_dict(d)
        assert e.name == "Imported"
        assert e.source_workflow_version == 3

    def test_from_dict_missing_version_raises(self):
        with pytest.raises(ValueError, match="Missing"):
            WorkflowExportData.from_dict({})

    def test_from_dict_wrong_major_version_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            WorkflowExportData.from_dict({"$nobla_version": "2.0"})

    def test_from_json(self):
        j = json.dumps({
            "$nobla_version": "1.0",
            "workflow": {"name": "J1", "steps": [{"ref_id": "a", "name": "A"}]},
        })
        e = WorkflowExportData.from_json(j)
        assert e.name == "J1"
        assert len(e.steps) == 1

    def test_from_json_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            WorkflowExportData.from_json("not json")

    def test_round_trip(self):
        e = WorkflowExportData(
            name="RT", description="Round trip",
            steps=[TemplateStep(ref_id="s1", name="S1", type="tool")],
            triggers=[TemplateTrigger(event_pattern="manual.*")],
            metadata={"key": "value"},
        )
        e2 = WorkflowExportData.from_json(e.to_json())
        assert e2.name == e.name
        assert e2.metadata == e.metadata
        assert len(e2.steps) == 1
        assert len(e2.triggers) == 1


# ===========================================================================
# Conversion helpers tests
# ===========================================================================


class TestConversionHelpers:

    def test_workflow_step_to_template_step(self):
        s = WorkflowStep(
            step_id="uuid-1", name="Build App", type=StepType.TOOL,
            config={"tool": "build"}, error_handling=ErrorHandling.RETRY,
            max_retries=2, timeout_seconds=60,
        )
        ts = workflow_step_to_template_step(s)
        assert ts.ref_id == "build_app"
        assert ts.type == "tool"
        assert ts.error_handling == "retry"
        assert ts.max_retries == 2
        assert ts.timeout_seconds == 60

    def test_workflow_step_with_ref_id_map(self):
        s1 = WorkflowStep(step_id="uuid-1", name="A", type=StepType.TOOL)
        s2 = WorkflowStep(step_id="uuid-2", name="B", type=StepType.TOOL, depends_on=["uuid-1"])
        ref_map = {"uuid-1": "step_a", "uuid-2": "step_b"}
        ts2 = workflow_step_to_template_step(s2, ref_map)
        assert ts2.ref_id == "step_b"
        assert ts2.depends_on == ["step_a"]

    def test_workflow_step_name_sanitization(self):
        s = WorkflowStep(step_id="x", name="Check CI/CD Status!", type=StepType.CONDITION)
        ts = workflow_step_to_template_step(s)
        assert ts.ref_id == "check_cicd_status"

    def test_workflow_step_empty_name_fallback(self):
        s = WorkflowStep(step_id="abcdef12-3456-7890", name="", type=StepType.TOOL)
        ts = workflow_step_to_template_step(s)
        assert ts.ref_id.startswith("step_")

    def test_workflow_trigger_to_template_trigger(self):
        t = WorkflowTrigger(
            trigger_id="tid", workflow_id="wid",
            event_pattern="webhook.github.*",
            conditions=[
                TriggerCondition(field_path="action", operator=ConditionOperator.EQ, value="push"),
            ],
        )
        tt = workflow_trigger_to_template_trigger(t)
        assert tt.event_pattern == "webhook.github.*"
        assert len(tt.conditions) == 1
        assert tt.conditions[0]["field_path"] == "action"
        assert tt.conditions[0]["operator"] == "eq"

    def test_workflow_trigger_no_conditions(self):
        t = WorkflowTrigger(event_pattern="manual.*")
        tt = workflow_trigger_to_template_trigger(t)
        assert tt.conditions == []


# ===========================================================================
# TemplateRegistry tests
# ===========================================================================


class TestTemplateRegistry:

    def test_loads_bundled_on_init(self):
        reg = TemplateRegistry(load_bundled=True)
        assert reg.count == 5
        for t in reg.list_all():
            assert t.bundled is True

    def test_no_bundled_on_init(self):
        reg = TemplateRegistry(load_bundled=False)
        assert reg.count == 0

    def test_register_custom(self):
        reg = TemplateRegistry(load_bundled=False)
        tmpl = WorkflowTemplate(name="Custom", category=TemplateCategory.CUSTOM)
        reg.register(tmpl)
        assert reg.count == 1
        assert reg.get(tmpl.template_id).name == "Custom"

    def test_register_duplicate_raises(self):
        reg = TemplateRegistry(load_bundled=False)
        tmpl = WorkflowTemplate(template_id="dup", name="Dup")
        reg.register(tmpl)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(WorkflowTemplate(template_id="dup", name="Dup2"))

    def test_get_nonexistent_raises(self):
        reg = TemplateRegistry(load_bundled=False)
        with pytest.raises(KeyError, match="not found"):
            reg.get("no-such")

    def test_delete_custom(self):
        reg = TemplateRegistry(load_bundled=False)
        tmpl = WorkflowTemplate(name="Del")
        reg.register(tmpl)
        reg.delete(tmpl.template_id)
        assert reg.count == 0

    def test_delete_bundled_raises(self):
        reg = TemplateRegistry(load_bundled=True)
        bundled = reg.list_all()[0]
        with pytest.raises(ValueError, match="bundled"):
            reg.delete(bundled.template_id)

    def test_delete_nonexistent_raises(self):
        reg = TemplateRegistry(load_bundled=False)
        with pytest.raises(KeyError):
            reg.delete("nope")

    def test_search_by_query(self):
        reg = TemplateRegistry(load_bundled=True)
        results = reg.search(query="pipeline")
        assert len(results) == 1
        assert results[0].name == "Data Pipeline"

    def test_search_by_category(self):
        reg = TemplateRegistry(load_bundled=True)
        results = reg.search(category=TemplateCategory.CI_CD)
        assert len(results) == 1
        assert results[0].name == "GitHub CI Notifier"

    def test_search_by_tags(self):
        reg = TemplateRegistry(load_bundled=True)
        results = reg.search(tags=["webhook"])
        assert len(results) >= 2  # CI Notifier + Webhook Relay

    def test_search_by_tags_and_category(self):
        reg = TemplateRegistry(load_bundled=True)
        results = reg.search(category=TemplateCategory.INTEGRATION, tags=["webhook"])
        assert len(results) == 1
        assert results[0].name == "Webhook Relay"

    def test_search_no_results(self):
        reg = TemplateRegistry(load_bundled=True)
        assert reg.search(query="zzz_nonexistent") == []

    def test_search_empty_returns_all(self):
        reg = TemplateRegistry(load_bundled=True)
        assert len(reg.search()) == 5

    def test_list_categories(self):
        reg = TemplateRegistry(load_bundled=True)
        cats = reg.list_categories()
        assert len(cats) >= 4
        for c in cats:
            assert "category" in c
            assert "label" in c
            assert "count" in c
            assert c["count"] > 0

    def test_list_all_sorted(self):
        reg = TemplateRegistry(load_bundled=True)
        names = [t.name for t in reg.list_all()]
        assert names == sorted(names)


# ===========================================================================
# Bundled templates validation
# ===========================================================================


class TestBundledTemplates:

    def setup_method(self):
        self.reg = TemplateRegistry(load_bundled=True)

    def test_github_ci_notifier(self):
        t = self.reg.get("bundled-github-ci-notifier")
        assert t.category == TemplateCategory.CI_CD
        assert len(t.steps) == 4
        assert len(t.triggers) == 1
        assert "github" in t.tags

    def test_scheduled_backup(self):
        t = self.reg.get("bundled-scheduled-backup")
        assert t.category == TemplateCategory.DEVOPS
        assert len(t.steps) == 4
        assert "backup" in t.tags

    def test_webhook_relay(self):
        t = self.reg.get("bundled-webhook-relay")
        assert t.category == TemplateCategory.INTEGRATION
        assert len(t.steps) == 3

    def test_approval_chain(self):
        t = self.reg.get("bundled-approval-chain")
        assert t.category == TemplateCategory.APPROVAL
        assert len(t.steps) == 4
        step_types = [s.type for s in t.steps]
        assert "approval" in step_types
        assert "condition" in step_types

    def test_data_pipeline(self):
        t = self.reg.get("bundled-data-pipeline")
        assert t.category == TemplateCategory.DATA_PIPELINE
        assert len(t.steps) == 4
        assert t.triggers[0].event_pattern == "schedule.hourly"

    def test_all_bundled_have_required_fields(self):
        for t in self.reg.list_all():
            assert t.name
            assert t.description
            assert t.author == "Nobla"
            assert t.icon
            assert len(t.steps) >= 3
            assert len(t.triggers) >= 1
            assert len(t.tags) >= 2

    def test_all_bundled_steps_have_deps_chain(self):
        """Verify steps form valid DAGs (no orphan deps)."""
        for t in self.reg.list_all():
            ref_ids = {s.ref_id for s in t.steps}
            for s in t.steps:
                for dep in s.depends_on:
                    assert dep in ref_ids, f"Step {s.ref_id} in {t.name} depends on unknown {dep}"

    def test_all_bundled_serializable(self):
        for t in self.reg.list_all():
            d = t.to_dict()
            t2 = WorkflowTemplate.from_dict(d)
            assert t2.name == t.name
            assert len(t2.steps) == len(t.steps)


# ===========================================================================
# Export / Import service tests
# ===========================================================================


class TestExportImportService:

    @pytest.fixture
    def svc_and_bus(self):
        svc, bus = _make_service()
        return svc, bus

    def test_export_basic(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        assert export.name == "Test WF"
        assert export.source_workflow_id == wf.workflow_id
        assert len(export.steps) == 2
        assert len(export.triggers) == 1

    def test_export_strips_uuids(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        for s in export.steps:
            assert s.ref_id != "s1" and s.ref_id != "s2"
            assert "-" not in s.ref_id  # No UUID-style dashes

    def test_export_remaps_depends_on(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        step2 = export.steps[1]
        assert step2.depends_on == [export.steps[0].ref_id]

    def test_export_includes_metadata(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id, include_metadata=True)
        assert "status" in export.metadata
        assert "version" in export.metadata

    def test_export_excludes_metadata(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id, include_metadata=False)
        assert export.metadata == {}

    def test_export_nonexistent_raises(self, svc_and_bus):
        svc, _ = svc_and_bus
        with pytest.raises(KeyError):
            svc.export_workflow("no-such")

    def test_export_to_json_round_trip(self, svc_and_bus):
        svc, _ = svc_and_bus
        wf = _make_workflow()
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        j = export.to_json()
        parsed = WorkflowExportData.from_json(j)
        assert parsed.name == export.name
        assert len(parsed.steps) == len(export.steps)

    def test_import_basic(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(
            name="Imported WF", description="Desc",
            steps=[
                TemplateStep(ref_id="a", name="A", type="tool", config={"tool": "t1"}),
                TemplateStep(ref_id="b", name="B", type="agent", depends_on=["a"]),
            ],
            triggers=[TemplateTrigger(event_pattern="manual.*")],
        )
        wf = svc.import_workflow(export_data, user_id="u2")
        assert wf.user_id == "u2"
        assert wf.name == "Imported WF"
        assert len(wf.steps) == 2
        assert len(wf.triggers) == 1

    def test_import_assigns_fresh_uuids(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(
            name="Fresh", steps=[TemplateStep(ref_id="x", name="X")],
        )
        wf = svc.import_workflow(export_data, user_id="u1")
        assert wf.steps[0].step_id != "x"
        assert len(wf.steps[0].step_id) == 36  # UUID format

    def test_import_remaps_depends_on(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(
            name="Deps",
            steps=[
                TemplateStep(ref_id="first", name="First"),
                TemplateStep(ref_id="second", name="Second", depends_on=["first"]),
            ],
        )
        wf = svc.import_workflow(export_data, user_id="u1")
        assert wf.steps[1].depends_on == [wf.steps[0].step_id]

    def test_import_with_name_override(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(name="Original")
        wf = svc.import_workflow(export_data, user_id="u1", name_override="Override")
        assert wf.name == "Override"

    def test_import_no_name_raises(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(name="")
        with pytest.raises(ValueError, match="name is required"):
            svc.import_workflow(export_data, user_id="u1")

    def test_import_preserves_trigger_conditions(self, svc_and_bus):
        svc, _ = svc_and_bus
        export_data = WorkflowExportData(
            name="Cond",
            triggers=[TemplateTrigger(
                event_pattern="webhook.*",
                conditions=[{"field_path": "action", "operator": "eq", "value": "push"}],
            )],
        )
        wf = svc.import_workflow(export_data, user_id="u1")
        assert len(wf.triggers) == 1
        assert len(wf.triggers[0].conditions) == 1
        assert wf.triggers[0].conditions[0].operator == ConditionOperator.EQ

    def test_import_user_limit(self, svc_and_bus):
        svc, _ = svc_and_bus
        svc._max_per_user = 1
        svc.import_workflow(
            WorkflowExportData(name="W1"),
            user_id="u1",
        )
        with pytest.raises(ValueError, match="maximum"):
            svc.import_workflow(
                WorkflowExportData(name="W2"),
                user_id="u1",
            )

    def test_full_export_import_round_trip(self, svc_and_bus):
        svc, _ = svc_and_bus
        # Create workflow
        wf = _make_workflow()
        svc.create(wf)
        # Export → JSON → Import
        export = svc.export_workflow(wf.workflow_id)
        json_str = export.to_json()
        reimported_data = WorkflowExportData.from_json(json_str)
        imported_wf = svc.import_workflow(reimported_data, user_id="u2")
        # Verify structure preserved
        assert imported_wf.name == wf.name
        assert len(imported_wf.steps) == len(wf.steps)
        assert len(imported_wf.triggers) == len(wf.triggers)
        # But IDs are different
        assert imported_wf.workflow_id != wf.workflow_id
        assert imported_wf.steps[0].step_id != wf.steps[0].step_id


# ===========================================================================
# Instantiate template tests
# ===========================================================================


class TestInstantiateTemplate:

    @pytest.fixture
    def svc_and_bus(self):
        svc, bus = _make_service()
        return svc, bus

    def test_instantiate_template(self, svc_and_bus):
        svc, _ = svc_and_bus
        tmpl = WorkflowTemplate(
            name="CI Notifier", description="Notify on CI",
            steps=[
                TemplateStep(ref_id="recv", name="Receive", type="webhook"),
                TemplateStep(ref_id="notify", name="Notify", type="tool", depends_on=["recv"]),
            ],
            triggers=[TemplateTrigger(event_pattern="webhook.github.*")],
        )
        wf = svc.instantiate_template(tmpl, user_id="u1")
        assert wf.name == "CI Notifier"
        assert wf.user_id == "u1"
        assert len(wf.steps) == 2
        assert wf.steps[1].depends_on == [wf.steps[0].step_id]

    def test_instantiate_with_name_override(self, svc_and_bus):
        svc, _ = svc_and_bus
        tmpl = WorkflowTemplate(name="Template")
        wf = svc.instantiate_template(tmpl, user_id="u1", name_override="Custom Name")
        assert wf.name == "Custom Name"


# ===========================================================================
# Gateway handler tests
# ===========================================================================


class TestTemplateHandlers:

    def setup_method(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from nobla.gateway.template_handlers import (
            create_template_router,
            set_template_registry,
            set_template_workflow_service,
        )

        self.svc, self.bus = _make_service()
        self.reg = TemplateRegistry(load_bundled=True)
        set_template_registry(self.reg)
        set_template_workflow_service(self.svc)
        app = FastAPI()
        app.include_router(create_template_router())
        self.client = TestClient(app)

    def test_list_templates(self):
        resp = self.client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5

    def test_list_templates_by_category(self):
        resp = self.client.get("/api/templates?category=ci_cd")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_templates_by_query(self):
        resp = self.client.get("/api/templates?query=pipeline")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_templates_by_tags(self):
        resp = self.client.get("/api/templates?tags=webhook")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_list_templates_invalid_category(self):
        resp = self.client.get("/api/templates?category=invalid")
        assert resp.status_code == 400

    def test_list_categories(self):
        resp = self.client.get("/api/templates/categories")
        assert resp.status_code == 200
        cats = resp.json()
        assert len(cats) >= 4

    def test_get_template_detail(self):
        resp = self.client.get("/api/templates/bundled-github-ci-notifier")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "GitHub CI Notifier"
        assert "steps" in data
        assert "triggers" in data
        assert "created_at" in data

    def test_get_template_not_found(self):
        resp = self.client.get("/api/templates/no-such")
        assert resp.status_code == 404

    def test_instantiate_template(self):
        resp = self.client.post(
            "/api/templates/bundled-github-ci-notifier/instantiate",
            json={"user_id": "u1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow_id" in data
        assert data["template_id"] == "bundled-github-ci-notifier"
        assert data["step_count"] == 4

    def test_instantiate_with_name_override(self):
        resp = self.client.post(
            "/api/templates/bundled-data-pipeline/instantiate",
            json={"name": "My Pipeline", "user_id": "u1"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Pipeline"

    def test_instantiate_not_found(self):
        resp = self.client.post("/api/templates/no-such/instantiate", json={})
        assert resp.status_code == 404

    def test_export_workflow(self):
        # Create workflow via instantiate
        cr = self.client.post(
            "/api/templates/bundled-webhook-relay/instantiate",
            json={"user_id": "u1"},
        )
        wf_id = cr.json()["workflow_id"]
        resp = self.client.get(f"/api/workflows/{wf_id}/export")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["$nobla_version"] == SCHEMA_VERSION
        assert data["workflow"]["name"] == "Webhook Relay"
        assert len(data["workflow"]["steps"]) == 3

    def test_export_not_found(self):
        resp = self.client.get("/api/workflows/no-such/export")
        assert resp.status_code == 404

    def test_import_workflow(self):
        export_json = {
            "$nobla_version": "1.0",
            "workflow": {
                "name": "Imported",
                "description": "From JSON",
                "steps": [
                    {"ref_id": "a", "name": "Step A", "type": "tool", "depends_on": [], "config": {}},
                ],
                "triggers": [{"event_pattern": "manual.*"}],
            },
            "source": {},
        }
        resp = self.client.post("/api/workflows/import", json={
            "data": export_json, "user_id": "u2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Imported"
        assert data["step_count"] == 1

    def test_import_with_name_override(self):
        export_json = {
            "$nobla_version": "1.0",
            "workflow": {"name": "Original", "steps": [], "triggers": []},
        }
        resp = self.client.post("/api/workflows/import", json={
            "data": export_json, "name": "Custom Name", "user_id": "u1",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Custom Name"

    def test_import_invalid_schema(self):
        resp = self.client.post("/api/workflows/import", json={
            "data": {"no_version": True}, "user_id": "u1",
        })
        assert resp.status_code == 400

    def test_export_import_round_trip_via_api(self):
        # Create from template
        cr = self.client.post(
            "/api/templates/bundled-approval-chain/instantiate",
            json={"user_id": "u1"},
        )
        wf_id = cr.json()["workflow_id"]
        # Export
        export_resp = self.client.get(f"/api/workflows/{wf_id}/export")
        export_data = export_resp.json()["data"]
        # Import as new user
        import_resp = self.client.post("/api/workflows/import", json={
            "data": export_data, "user_id": "u3", "name": "Cloned",
        })
        assert import_resp.status_code == 200
        cloned = import_resp.json()
        assert cloned["name"] == "Cloned"
        assert cloned["step_count"] == 4
        assert cloned["workflow_id"] != wf_id


# ===========================================================================
# Export deduplication edge case
# ===========================================================================


class TestExportEdgeCases:

    def test_duplicate_step_names_get_unique_refs(self):
        svc, _ = _make_service()
        wf = Workflow(
            user_id="u1", name="Dup Names",
            steps=[
                WorkflowStep(step_id="s1", name="Process", type=StepType.TOOL),
                WorkflowStep(step_id="s2", name="Process", type=StepType.TOOL),
                WorkflowStep(step_id="s3", name="Process", type=StepType.TOOL),
            ],
        )
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        ref_ids = [s.ref_id for s in export.steps]
        assert len(set(ref_ids)) == 3  # All unique

    def test_export_preserves_step_config(self):
        svc, _ = _make_service()
        wf = Workflow(
            user_id="u1", name="Config Test",
            steps=[
                WorkflowStep(
                    step_id="s1", name="Complex", type=StepType.CONDITION,
                    config={"branches": [{"name": "a", "condition": {"field": "x"}}]},
                ),
            ],
        )
        svc.create(wf)
        export = svc.export_workflow(wf.workflow_id)
        assert export.steps[0].config["branches"][0]["name"] == "a"

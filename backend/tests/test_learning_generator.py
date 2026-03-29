"""Tests for Phase 5B.1 SkillGenerator — macro creation, promotion, publishing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.learning.generator import SkillGenerator
from nobla.learning.models import (
    MacroParameter,
    MacroTier,
    PatternCandidate,
    PatternOccurrence,
    PatternStatus,
    WorkflowMacro,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def workflow_service():
    svc = AsyncMock()
    svc.create_from_steps = AsyncMock(return_value="wf-123")
    return svc


@pytest.fixture
def skill_runtime():
    rt = AsyncMock()
    manifest = MagicMock()
    manifest.id = "skill-123"
    rt.install = AsyncMock(return_value=manifest)
    return rt


@pytest.fixture
def security_scanner():
    scanner = AsyncMock()
    scan_result = MagicMock()
    scan_result.passed = True
    scan_result.issues = []
    scanner.scan = AsyncMock(return_value=scan_result)
    return scanner


@pytest.fixture
def llm_router():
    router = AsyncMock()
    router.route = AsyncMock(return_value=MagicMock(
        content="def execute(params): return {'result': 'ok'}"
    ))
    return router


@pytest.fixture
def generator(event_bus, workflow_service, skill_runtime, security_scanner, llm_router):
    return SkillGenerator(
        event_bus=event_bus,
        workflow_service=workflow_service,
        skill_runtime=skill_runtime,
        security_scanner=security_scanner,
        llm_router=llm_router,
    )


def _make_pattern():
    return PatternCandidate(
        id=str(uuid.uuid4()),
        user_id="user-1",
        fingerprint="abc123",
        description="file.manage → code.run",
        occurrences=[
            PatternOccurrence(
                timestamp=datetime.now(timezone.utc),
                conversation_id="conv-1",
                params={"path": "/app"},
            ),
        ],
        tool_sequence=["file.manage", "code.run"],
        variable_params={"path": ["/app", "/tmp", "/home"]},
        status=PatternStatus.CONFIRMED,
        confidence=0.85,
        detection_method="sequence",
        created_at=datetime.now(timezone.utc),
    )


class TestCreateMacro:
    @pytest.mark.asyncio
    async def test_creates_macro_from_pattern(self, generator, workflow_service):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        assert macro.tier == MacroTier.MACRO
        assert macro.pattern_id == pattern.id
        assert macro.workflow_id == "wf-123"
        assert macro.user_id == "user-1"
        assert macro.skill_id is None
        workflow_service.create_from_steps.assert_called_once()

    @pytest.mark.asyncio
    async def test_extracts_parameters(self, generator):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        param_names = [p.name for p in macro.parameters]
        assert "path" in param_names

    @pytest.mark.asyncio
    async def test_emits_macro_created_event(self, generator, event_bus):
        pattern = _make_pattern()
        await generator.create_macro(pattern)
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "learning.macro.created"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_generates_name_and_description(self, generator):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        assert macro.name  # not empty
        assert macro.description  # not empty


class TestPromoteToSkill:
    @pytest.mark.asyncio
    async def test_promotes_macro_to_skill(self, generator, security_scanner, skill_runtime):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        result = await generator.promote_to_skill(macro.id)
        assert result is not None
        updated = (await generator.get_macros("user-1"))[0]
        assert updated.tier == MacroTier.SKILL
        assert updated.skill_id == "skill-123"
        assert updated.promoted_at is not None

    @pytest.mark.asyncio
    async def test_emits_skill_promoted_event(self, generator, event_bus):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        event_bus.emit.reset_mock()
        await generator.promote_to_skill(macro.id)
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "learning.skill.promoted"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_scanner_rejection_prevents_install(self, generator, security_scanner, skill_runtime):
        scan_result = MagicMock()
        scan_result.passed = False
        scan_result.issues = ["dangerous pattern"]
        security_scanner.scan = AsyncMock(return_value=scan_result)

        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        result = await generator.promote_to_skill(macro.id)
        assert result is None
        skill_runtime.install.assert_not_called()
        updated = (await generator.get_macros("user-1"))[0]
        assert updated.tier == MacroTier.MACRO  # not promoted


class TestMarkPublishable:
    @pytest.mark.asyncio
    async def test_marks_as_publishable(self, generator):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        await generator.promote_to_skill(macro.id)
        result = await generator.mark_publishable(macro.id, {"tags": ["deploy"]})
        assert result.tier == MacroTier.PUBLISHABLE

    @pytest.mark.asyncio
    async def test_emits_publishable_event(self, generator, event_bus):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        await generator.promote_to_skill(macro.id)
        event_bus.emit.reset_mock()
        await generator.mark_publishable(macro.id, {"tags": ["deploy"]})
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "learning.skill.publishable"]
        assert len(calls) == 1


class TestGetAndDeleteMacros:
    @pytest.mark.asyncio
    async def test_get_macros_filters_by_tier(self, generator):
        p1 = _make_pattern()
        p2 = _make_pattern()
        await generator.create_macro(p1)
        m2 = await generator.create_macro(p2)
        await generator.promote_to_skill(m2.id)
        macros = await generator.get_macros("user-1", tier=MacroTier.MACRO)
        skills = await generator.get_macros("user-1", tier=MacroTier.SKILL)
        assert len(macros) == 1
        assert len(skills) == 1

    @pytest.mark.asyncio
    async def test_delete_macro(self, generator):
        pattern = _make_pattern()
        macro = await generator.create_macro(pattern)
        await generator.delete_macro(macro.id)
        macros = await generator.get_macros("user-1")
        assert len(macros) == 0

"""Tests for the Skill Runtime (Phase 5-Foundation §4.3).

Covers: SkillManifest, SkillCategory, SkillToolBridge, UniversalSkillAdapter,
NoblaAdapter, SkillRuntime, SkillSecurityScanner.
"""

from __future__ import annotations

from typing import Any

import pytest

from nobla.security.permissions import Tier
from nobla.skills.adapter import UniversalSkillAdapter
from nobla.skills.adapters.nobla import NoblaAdapter
from nobla.skills.bridge import SkillToolBridge
from nobla.skills.models import (
    NoblaSkill,
    SkillCategory,
    SkillManifest,
    SkillSource,
)
from nobla.skills.runtime import SecurityError, SkillRuntime
from nobla.skills.security import SkillSecurityScanner
from nobla.tools.models import ToolCategory, ToolParams
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY
from nobla.gateway.websocket import ConnectionState


def _params(**args: Any) -> ToolParams:
    """Build ToolParams with a dummy ConnectionState."""
    return ToolParams(args=args, connection_state=ConnectionState())


# ── Helpers ────────────────────────────────────────────────


def _make_manifest(**overrides: Any) -> SkillManifest:
    defaults = dict(
        id="nobla://test-skill",
        name="test.skill",
        description="A test skill",
        version="1.0.0",
        source=SkillSource.NOBLA,
        author="test",
        category=SkillCategory.UTILITIES,
        tier=Tier.STANDARD,
        requires_approval=True,
        enabled=False,
    )
    defaults.update(overrides)
    return SkillManifest(**defaults)


class FakeSkill(NoblaSkill):
    """Minimal NoblaSkill for testing."""

    def __init__(self, manifest: SkillManifest | None = None) -> None:
        self.manifest = manifest or _make_manifest()
        self.last_params: dict | None = None

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        self.last_params = params
        return {"result": "ok"}

    async def validate(self, params: dict[str, Any]) -> None:
        if "invalid" in params:
            raise ValueError("Invalid parameter")


def _nobla_source_dict(**overrides: Any) -> dict:
    """Create a native Nobla skill manifest dict."""
    defaults = dict(
        nobla_version="1.0",
        name="my.skill",
        description="Test skill",
        version="0.1.0",
        author="tester",
        category="utilities",
        tier="STANDARD",
        requires_approval=True,
    )
    defaults.update(overrides)
    return defaults


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure each test starts with a clean tool registry."""
    _TOOL_REGISTRY.clear()
    yield
    _TOOL_REGISTRY.clear()


# ── SkillManifest / SkillCategory tests ───────────────────


class TestSkillModels:
    def test_manifest_defaults(self):
        m = _make_manifest()
        assert m.enabled is False
        assert m.requires_approval is True
        assert m.capabilities == []
        assert m.dependencies == []

    def test_skill_category_maps_to_tool_category(self):
        assert SkillCategory.CODE.to_tool_category() == ToolCategory.CODE
        assert SkillCategory.VISION.to_tool_category() == ToolCategory.VISION

    def test_marketplace_category_maps_to_skill(self):
        assert SkillCategory.FINANCE.to_tool_category() == ToolCategory.SKILL
        assert SkillCategory.PRODUCTIVITY.to_tool_category() == ToolCategory.SKILL
        assert SkillCategory.MEDIA.to_tool_category() == ToolCategory.SKILL

    def test_skill_source_values(self):
        assert SkillSource.NOBLA.value == "nobla"
        assert SkillSource.MCP.value == "mcp"
        assert SkillSource.OPENCLAW.value == "openclaw"

    def test_fake_skill_execute(self):
        skill = FakeSkill()
        assert skill.manifest.name == "test.skill"

    def test_describe_action_default(self):
        skill = FakeSkill()
        assert "test.skill" in skill.describe_action({})

    def test_params_summary_strips_secrets(self):
        skill = FakeSkill()
        summary = skill.get_params_summary(
            {"api_key": "abc", "secret_token": "xyz", "query": "hello"}
        )
        assert "query" in summary
        assert "secret_token" not in summary


# ── SkillToolBridge tests ─────────────────────────────────


class TestSkillToolBridge:
    def test_maps_manifest_to_base_tool(self):
        manifest = _make_manifest(
            tier=Tier.ELEVATED, category=SkillCategory.CODE
        )
        skill = FakeSkill(manifest)
        bridge = SkillToolBridge(skill)

        assert bridge.name == "test.skill"
        assert bridge.description == "A test skill"
        assert bridge.category == ToolCategory.CODE
        assert bridge.tier == Tier.ELEVATED
        assert bridge.requires_approval is True

    @pytest.mark.asyncio
    async def test_execute_delegates_to_skill(self):
        skill = FakeSkill()
        bridge = SkillToolBridge(skill)
        result = await bridge.execute(_params(query="test"))

        assert result.success is True
        assert result.data == {"result": "ok"}
        assert skill.last_params == {"query": "test"}

    @pytest.mark.asyncio
    async def test_execute_handles_skill_error(self):
        manifest = _make_manifest()

        class FailingSkill(NoblaSkill):
            def __init__(self):
                self.manifest = manifest

            async def execute(self, params):
                raise RuntimeError("boom")

            async def validate(self, params):
                pass

        bridge = SkillToolBridge(FailingSkill())
        result = await bridge.execute(_params())

        assert result.success is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_validate_delegates(self):
        skill = FakeSkill()
        bridge = SkillToolBridge(skill)
        # Valid params — should not raise
        await bridge.validate(_params(query="ok"))

        # Invalid params
        with pytest.raises(ValueError, match="Invalid parameter"):
            await bridge.validate(_params(invalid=True))

    def test_bridge_has_manifest_and_skill(self):
        skill = FakeSkill()
        bridge = SkillToolBridge(skill)
        assert bridge.manifest is skill.manifest
        assert bridge.skill is skill


# ── UniversalSkillAdapter tests ───────────────────────────


class TestUniversalSkillAdapter:
    def test_detect_nobla_format(self):
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        assert adapter.detect_format(_nobla_source_dict()) == SkillSource.NOBLA

    def test_detect_unknown_format(self):
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        assert adapter.detect_format({"random": "data"}) is None

    @pytest.mark.asyncio
    async def test_import_nobla_skill(self):
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        skill = await adapter.import_skill(_nobla_source_dict(name="hello.world"))
        assert skill.manifest.name == "hello.world"
        assert skill.manifest.source == SkillSource.NOBLA
        assert skill.manifest.enabled is False

    @pytest.mark.asyncio
    async def test_import_unknown_raises(self):
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        with pytest.raises(ValueError, match="No adapter"):
            await adapter.import_skill({"random": "data"})

    @pytest.mark.asyncio
    async def test_import_preserves_original_format(self):
        source = _nobla_source_dict(name="preserve.test")
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        skill = await adapter.import_skill(source)
        assert skill.manifest.original_format == source


# ── NoblaAdapter tests ────────────────────────────────────


class TestNoblaAdapter:
    def test_can_handle_valid(self):
        adapter = NoblaAdapter()
        assert adapter.can_handle(_nobla_source_dict()) is True

    def test_cannot_handle_missing_version(self):
        adapter = NoblaAdapter()
        assert adapter.can_handle({"name": "test"}) is False

    def test_cannot_handle_string(self):
        adapter = NoblaAdapter()
        assert adapter.can_handle("not a json string") is False

    @pytest.mark.asyncio
    async def test_import_parses_all_fields(self):
        adapter = NoblaAdapter()
        skill = await adapter.import_skill(
            _nobla_source_dict(
                name="full.skill",
                description="Full test",
                author="author1",
                category="code",
                tier="ELEVATED",
                capabilities=["exec"],
                dependencies=["numpy"],
            )
        )
        m = skill.manifest
        assert m.name == "full.skill"
        assert m.description == "Full test"
        assert m.author == "author1"
        assert m.category == SkillCategory.CODE
        assert m.tier == Tier.ELEVATED
        assert m.capabilities == ["exec"]
        assert m.dependencies == ["numpy"]

    @pytest.mark.asyncio
    async def test_import_defaults(self):
        adapter = NoblaAdapter()
        skill = await adapter.import_skill(
            {"nobla_version": "1.0", "name": "minimal"}
        )
        assert skill.manifest.version == "0.1.0"
        assert skill.manifest.author == "unknown"
        assert skill.manifest.category == SkillCategory.UTILITIES


# ── SkillRuntime tests ────────────────────────────────────


class TestSkillRuntime:
    def _make_runtime(self, scanner=None, event_bus=None):
        registry = ToolRegistry()
        adapter = UniversalSkillAdapter([NoblaAdapter()])
        return SkillRuntime(
            tool_registry=registry,
            adapter=adapter,
            event_bus=event_bus,
            security_scanner=scanner,
        ), registry

    @pytest.mark.asyncio
    async def test_install(self):
        rt, registry = self._make_runtime()
        manifest = await rt.install(_nobla_source_dict(name="install.test"))

        assert manifest.name == "install.test"
        assert manifest.enabled is False
        assert rt.is_installed(manifest.id)
        assert registry.get("install.test") is not None

    @pytest.mark.asyncio
    async def test_install_duplicate_raises(self):
        rt, _ = self._make_runtime()
        await rt.install(_nobla_source_dict(name="dup"))
        with pytest.raises(ValueError, match="already installed"):
            await rt.install(_nobla_source_dict(name="dup"))

    @pytest.mark.asyncio
    async def test_uninstall(self):
        rt, registry = self._make_runtime()
        manifest = await rt.install(_nobla_source_dict(name="remove.me"))
        await rt.uninstall(manifest.id)

        assert not rt.is_installed(manifest.id)
        assert registry.get("remove.me") is None

    @pytest.mark.asyncio
    async def test_uninstall_nonexistent_raises(self):
        rt, _ = self._make_runtime()
        with pytest.raises(KeyError):
            await rt.uninstall("nobla://nonexistent")

    @pytest.mark.asyncio
    async def test_enable_disable(self):
        rt, _ = self._make_runtime()
        manifest = await rt.install(_nobla_source_dict(name="toggle"))

        assert not rt.is_enabled(manifest.id)
        await rt.enable(manifest.id)
        assert rt.is_enabled(manifest.id)
        await rt.disable(manifest.id)
        assert not rt.is_enabled(manifest.id)

    @pytest.mark.asyncio
    async def test_list_installed(self):
        rt, _ = self._make_runtime()
        await rt.install(_nobla_source_dict(name="skill.a"))
        await rt.install(_nobla_source_dict(name="skill.b", id="nobla://b"))

        installed = await rt.list_installed()
        names = [m.name for m in installed]
        assert "skill.a" in names
        assert "skill.b" in names

    @pytest.mark.asyncio
    async def test_upgrade(self):
        rt, registry = self._make_runtime()
        v1 = await rt.install(
            _nobla_source_dict(name="upgradable", version="1.0.0")
        )
        await rt.enable(v1.id)

        v2 = await rt.upgrade(
            v1.id,
            _nobla_source_dict(name="upgradable", version="2.0.0"),
        )
        assert v2.version == "2.0.0"
        assert rt.is_enabled(v2.id)  # Preserved enabled state

    @pytest.mark.asyncio
    async def test_install_with_failing_scanner(self):
        from nobla.skills.security import ScanResult, SkillSecurityScanner

        class FailScanner:
            async def scan(self, manifest, source_code=None):
                return ScanResult(passed=False, issues=["blocked"])

        rt, _ = self._make_runtime(scanner=FailScanner())
        with pytest.raises(SecurityError, match="failed security scan"):
            await rt.install(_nobla_source_dict(name="bad.skill"))

    @pytest.mark.asyncio
    async def test_install_emits_event(self):
        events: list = []

        class FakeBus:
            async def emit(self, event):
                events.append(event)

        rt, _ = self._make_runtime(event_bus=FakeBus())
        await rt.install(_nobla_source_dict(name="evented"))

        assert len(events) == 1
        assert events[0].event_type == "skill.installed"
        assert events[0].payload["name"] == "evented"


# ── SkillSecurityScanner tests ────────────────────────────


class TestSkillSecurityScanner:
    def _scanner(self):
        return SkillSecurityScanner()

    @pytest.mark.asyncio
    async def test_clean_manifest_passes(self):
        scanner = self._scanner()
        result = await scanner.scan(_make_manifest())
        assert result.passed is True
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_blocked_dependency(self):
        scanner = self._scanner()
        manifest = _make_manifest(dependencies=["numpy", "evil-package>=1.0"])
        result = await scanner.scan(manifest)
        assert not result.passed
        assert any("evil-package" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_admin_without_approval_fails(self):
        scanner = self._scanner()
        manifest = _make_manifest(tier=Tier.ADMIN, requires_approval=False)
        result = await scanner.scan(manifest)
        assert not result.passed
        assert any("ADMIN" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_admin_with_approval_passes(self):
        scanner = self._scanner()
        manifest = _make_manifest(tier=Tier.ADMIN, requires_approval=True)
        result = await scanner.scan(manifest)
        assert result.passed

    @pytest.mark.asyncio
    async def test_elevated_tier_warning(self):
        scanner = self._scanner()
        manifest = _make_manifest(tier=Tier.ELEVATED)
        result = await scanner.scan(manifest)
        assert result.passed  # Warning, not failure
        assert any("ELEVATED" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_source_code_patterns(self):
        scanner = self._scanner()
        code = """
import os
token = os.environ['SECRET']
result = eval(user_input)
"""
        result = await scanner.scan(_make_manifest(), source_code=code)
        assert result.passed  # Patterns are warnings, not failures
        assert len(result.patterns_found) >= 2
        assert any("environment" in p.lower() for p in result.patterns_found)
        assert any("eval" in p.lower() for p in result.patterns_found)

    @pytest.mark.asyncio
    async def test_empty_name_fails(self):
        scanner = self._scanner()
        manifest = _make_manifest(name="")
        result = await scanner.scan(manifest)
        assert not result.passed
        assert any("name" in i.lower() for i in result.issues)

    @pytest.mark.asyncio
    async def test_pre_enabled_fails(self):
        scanner = self._scanner()
        manifest = _make_manifest(enabled=True)
        result = await scanner.scan(manifest)
        assert not result.passed
        assert any("enabled" in i.lower() for i in result.issues)

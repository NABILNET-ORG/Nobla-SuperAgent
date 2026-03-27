# backend/tests/integration/test_phase5_foundation.py
"""End-to-end integration tests for Phase 5-Foundation components.

Validates:
- Event bus → channel manager → skill runtime pipeline
- Tool executor → event bus event emission
- Cross-component event propagation
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from nobla.channels.base import BaseChannelAdapter, ChannelMessage, ChannelResponse
from nobla.channels.manager import ChannelManager
from nobla.channels.linking import UserLinkingService
from nobla.events.bus import NoblaEventBus
from nobla.events.models import NoblaEvent
from nobla.security.permissions import PermissionChecker, Tier
from nobla.skills.adapter import UniversalSkillAdapter
from nobla.skills.adapters.nobla import NoblaAdapter
from nobla.skills.runtime import SkillRuntime
from nobla.skills.security import SkillSecurityScanner
from nobla.tools.approval import ApprovalManager
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import (
    ConnectionState,
    ToolCategory,
    ToolParams,
    ToolResult,
)
from nobla.tools.base import BaseTool
from nobla.tools.registry import ToolRegistry


# ── Test Fixtures ──────────────────────────────────────────────


class _EchoTool(BaseTool):
    """Minimal tool that echoes input for testing."""

    name = "test.echo"
    description = "Echo tool for integration tests"
    category = ToolCategory.SEARCH
    tier = Tier.SAFE

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data={"echo": params.args.get("msg", "")})

    async def validate(self, params: ToolParams) -> None:
        pass


class _FailTool(BaseTool):
    """Tool that always raises for testing failure events."""

    name = "test.fail"
    description = "Failing tool for integration tests"
    category = ToolCategory.SEARCH
    tier = Tier.SAFE

    async def execute(self, params: ToolParams) -> ToolResult:
        raise RuntimeError("deliberate failure")

    async def validate(self, params: ToolParams) -> None:
        pass


class _StubChannel(BaseChannelAdapter):
    """In-memory channel adapter for testing."""

    def __init__(self, channel_id: str = "test-channel"):
        self._id = channel_id
        self._started = False
        self.sent: list[ChannelResponse] = []

    @property
    def name(self) -> str:
        return self._id

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def send(self, channel_user_id: str, response: ChannelResponse) -> None:
        self.sent.append(response)

    async def send_notification(self, channel_user_id: str, text: str) -> None:
        pass

    def parse_callback(self, raw_callback) -> tuple[str, dict]:
        return ("noop", {})

    async def health_check(self) -> bool:
        return self._started


def _make_params(user_id: str = "user-1", msg: str = "hello") -> ToolParams:
    return ToolParams(
        args={"msg": msg},
        connection_state=ConnectionState(
            connection_id="conn-1",
            user_id=user_id,
            tier=Tier.SAFE,
        ),
    )


@pytest.fixture
async def event_bus():
    bus = NoblaEventBus(max_queue_depth=1000)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    reg.register(_FailTool())
    yield reg
    reg.unregister("test.echo")
    reg.unregister("test.fail")


@pytest.fixture
def tool_executor(tool_registry, event_bus):
    return ToolExecutor(
        registry=tool_registry,
        permission_checker=PermissionChecker(),
        audit_logger=AsyncMock(),
        approval_manager=ApprovalManager(connection_manager=None),
        event_bus=event_bus,
    )


@pytest.fixture
def channel_manager():
    linking = UserLinkingService()
    return ChannelManager(linking_service=linking)


@pytest.fixture
def skill_runtime(tool_registry, event_bus):
    adapter = UniversalSkillAdapter([NoblaAdapter()])
    scanner = SkillSecurityScanner()
    return SkillRuntime(
        tool_registry=tool_registry,
        adapter=adapter,
        event_bus=event_bus,
        security_scanner=scanner,
    )


# ── Tests ──────────────────────────────────────────────────────


class TestEventBusPipeline:
    """Event bus propagates events across components."""

    @pytest.mark.asyncio
    async def test_tool_executed_event_reaches_subscriber(
        self, event_bus, tool_executor
    ):
        """tool.executed event is emitted and received by a subscriber."""
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent):
            received.append(event)

        event_bus.subscribe("tool.executed", handler)

        result = await tool_executor.execute("test.echo", _make_params(msg="hi"))
        assert result.success is True

        # Give the bus a tick to dispatch
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].event_type == "tool.executed"
        assert received[0].source == "tool.test.echo"
        assert received[0].payload["tool_name"] == "test.echo"
        assert received[0].payload["success"] is True
        assert received[0].user_id == "user-1"

    @pytest.mark.asyncio
    async def test_tool_failed_event_reaches_subscriber(
        self, event_bus, tool_executor
    ):
        """tool.failed event is emitted when a tool raises."""
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent):
            received.append(event)

        event_bus.subscribe("tool.failed", handler)

        result = await tool_executor.execute("test.fail", _make_params())
        assert result.success is False

        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].event_type == "tool.failed"
        assert received[0].source == "tool.test.fail"
        assert received[0].payload["success"] is False
        assert "deliberate failure" in received[0].payload["error"]

    @pytest.mark.asyncio
    async def test_wildcard_subscriber_receives_both_events(
        self, event_bus, tool_executor
    ):
        """Wildcard tool.* captures both executed and failed events."""
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent):
            received.append(event)

        event_bus.subscribe("tool.*", handler)

        await tool_executor.execute("test.echo", _make_params())
        await tool_executor.execute("test.fail", _make_params())
        await asyncio.sleep(0.05)

        types = {e.event_type for e in received}
        assert "tool.executed" in types
        assert "tool.failed" in types

    @pytest.mark.asyncio
    async def test_correlation_id_propagated(self, event_bus, tool_executor):
        """Each execution gets a unique correlation_id in its event."""
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent):
            received.append(event)

        event_bus.subscribe("tool.*", handler)

        await tool_executor.execute("test.echo", _make_params())
        await tool_executor.execute("test.echo", _make_params())
        await asyncio.sleep(0.05)

        assert len(received) == 2
        assert received[0].correlation_id != received[1].correlation_id


class TestChannelManagerIntegration:
    """Channel manager works with the event bus lifecycle."""

    @pytest.mark.asyncio
    async def test_channel_register_start_stop(self, channel_manager):
        """Channels can be registered, started, and stopped."""
        ch = _StubChannel("telegram")
        channel_manager.register(ch)

        await channel_manager.start_all()
        assert await ch.health_check() is True

        await channel_manager.stop_all()
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_channel_events_on_tool_execution(
        self, event_bus, tool_executor, channel_manager
    ):
        """Channel manager can subscribe to tool events from the bus."""
        notifications: list[NoblaEvent] = []

        async def channel_notifier(event: NoblaEvent):
            notifications.append(event)

        event_bus.subscribe("tool.executed", channel_notifier)

        ch = _StubChannel("slack")
        channel_manager.register(ch)
        await channel_manager.start_all()

        await tool_executor.execute("test.echo", _make_params())
        await asyncio.sleep(0.05)

        assert len(notifications) == 1
        assert notifications[0].payload["tool_name"] == "test.echo"

        await channel_manager.stop_all()


class TestSkillRuntimeIntegration:
    """Skill runtime interacts with tool registry and event bus."""

    @pytest.mark.asyncio
    async def test_skill_install_emits_event(self, event_bus, skill_runtime):
        """Installing a skill emits a skill.installed event."""
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent):
            received.append(event)

        event_bus.subscribe("skill.*", handler)

        manifest_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "description": "Integration test skill",
            "entry_point": "test_module",
            "nobla_version": "1",
        }
        await skill_runtime.install(manifest_data)

        await asyncio.sleep(0.05)

        installed_events = [
            e for e in received if e.event_type == "skill.installed"
        ]
        assert len(installed_events) == 1
        assert installed_events[0].payload["name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_skill_registers_in_tool_registry(
        self, tool_registry, skill_runtime
    ):
        """Installed skill appears as a tool via the bridge."""
        manifest_data = {
            "name": "bridge-test",
            "version": "1.0.0",
            "description": "Bridge integration test",
            "entry_point": "bridge_test_mod",
            "nobla_version": "1",
        }
        await skill_runtime.install(manifest_data)

        tool = tool_registry.get("bridge-test")
        assert tool is not None
        assert tool.category == ToolCategory.SKILL


class TestFullPipeline:
    """End-to-end: event bus → tool executor → channel notification."""

    @pytest.mark.asyncio
    async def test_tool_execution_triggers_full_pipeline(
        self, event_bus, tool_executor
    ):
        """Complete pipeline: execute tool → event emitted → subscriber notified."""
        # Simulate a channel adapter reacting to tool events
        activity_log: list[dict] = []

        async def activity_feed_handler(event: NoblaEvent):
            activity_log.append({
                "tool": event.payload["tool_name"],
                "success": event.payload["success"],
                "time_ms": event.payload["execution_time_ms"],
            })

        event_bus.subscribe("tool.executed", activity_feed_handler)

        # Execute
        result = await tool_executor.execute(
            "test.echo", _make_params(msg="pipeline")
        )
        assert result.success is True
        assert result.data["echo"] == "pipeline"

        await asyncio.sleep(0.05)

        # Verify the full pipeline delivered the event
        assert len(activity_log) == 1
        assert activity_log[0]["tool"] == "test.echo"
        assert activity_log[0]["success"] is True
        assert activity_log[0]["time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self, event_bus, tool_executor):
        """Multiple independent subscribers all get the same event."""
        log_a: list[str] = []
        log_b: list[str] = []
        log_c: list[str] = []

        async def handler_a(e: NoblaEvent):
            log_a.append(e.event_type)

        async def handler_b(e: NoblaEvent):
            log_b.append(e.event_type)

        async def handler_c(e: NoblaEvent):
            log_c.append(e.event_type)

        event_bus.subscribe("tool.executed", handler_a)
        event_bus.subscribe("tool.executed", handler_b)
        event_bus.subscribe("tool.*", handler_c)

        await tool_executor.execute("test.echo", _make_params())
        await asyncio.sleep(0.05)

        assert log_a == ["tool.executed"]
        assert log_b == ["tool.executed"]
        assert log_c == ["tool.executed"]

    @pytest.mark.asyncio
    async def test_event_bus_handler_isolation(self, event_bus, tool_executor):
        """A failing handler does not break other handlers."""
        good_log: list[str] = []

        async def bad_handler(e: NoblaEvent):
            raise ValueError("handler crash")

        async def good_handler(e: NoblaEvent):
            good_log.append(e.event_type)

        event_bus.subscribe("tool.executed", bad_handler)
        event_bus.subscribe("tool.executed", good_handler)

        result = await tool_executor.execute("test.echo", _make_params())
        assert result.success is True

        await asyncio.sleep(0.05)

        # Good handler still received the event despite bad_handler crashing
        assert good_log == ["tool.executed"]

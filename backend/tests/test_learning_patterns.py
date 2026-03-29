"""Tests for Phase 5B.1 PatternDetector — sequence matching + intent clustering."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.patterns import PatternDetector
from nobla.learning.models import PatternCandidate, PatternConfig, PatternStatus


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def config():
    return PatternConfig(min_occurrences=3, sequence_window_days=7)


@pytest.fixture
def detector(event_bus, config):
    return PatternDetector(event_bus=event_bus, config=config)


def _tool_event(tool_name, user_id="user-1", correlation_id="corr-1", params=None):
    event = MagicMock()
    event.event_type = "tool.executed"
    event.payload = {"tool_name": tool_name, "params": params or {}, "user_id": user_id}
    event.user_id = user_id
    event.correlation_id = correlation_id
    event.timestamp = datetime.now(timezone.utc)
    return event


class TestFingerprinting:
    def test_same_sequence_same_fingerprint(self, detector):
        fp1 = detector.compute_fingerprint(["file.manage", "code.run"])
        fp2 = detector.compute_fingerprint(["file.manage", "code.run"])
        assert fp1 == fp2

    def test_different_sequence_different_fingerprint(self, detector):
        fp1 = detector.compute_fingerprint(["file.manage", "code.run"])
        fp2 = detector.compute_fingerprint(["code.run", "file.manage"])
        assert fp1 != fp2

    def test_fingerprint_is_hex_digest(self, detector):
        fp = detector.compute_fingerprint(["file.manage"])
        assert len(fp) == 64  # SHA-256 hex


class TestSequenceDetection:
    @pytest.mark.asyncio
    async def test_no_pattern_below_threshold(self, detector, event_bus):
        for corr_id in ["c1", "c2"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert len(patterns) == 0

    @pytest.mark.asyncio
    async def test_pattern_detected_at_threshold(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert len(patterns) == 1
        assert patterns[0].status == PatternStatus.DETECTED
        assert patterns[0].tool_sequence == ["file.manage", "code.run"]

    @pytest.mark.asyncio
    async def test_pattern_emits_detected_event(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.pattern.detected"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_variable_params_extracted(self, detector, event_bus):
        for i, corr_id in enumerate(["c1", "c2", "c3"]):
            await detector.on_tool_executed(_tool_event("file.manage", correlation_id=corr_id, params={"path": f"/dir{i}"}))
            await detector.on_tool_executed(_tool_event("code.run", correlation_id=corr_id, params={"code": "print('hi')"}))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert "path" in patterns[0].variable_params


class TestDismissPattern:
    @pytest.mark.asyncio
    async def test_dismiss_sets_status(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        await detector.dismiss_pattern(patterns[0].id)
        updated = await detector.get_patterns("user-1", status=PatternStatus.DISMISSED)
        assert len(updated) == 1

    @pytest.mark.asyncio
    async def test_dismiss_emits_event(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        event_bus.emit.reset_mock()
        await detector.dismiss_pattern(patterns[0].id)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.pattern.dismissed"]
        assert len(calls) == 1


class TestMaxPatternsPerUser:
    @pytest.mark.asyncio
    async def test_cap_enforced(self, event_bus):
        config = PatternConfig(min_occurrences=3, max_patterns_per_user=2)
        det = PatternDetector(event_bus=event_bus, config=config)
        for seq_idx in range(3):
            tools = [f"tool_{seq_idx}_a", f"tool_{seq_idx}_b"]
            for corr_id in [f"c{seq_idx}_1", f"c{seq_idx}_2", f"c{seq_idx}_3"]:
                for tool in tools:
                    await det.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
                await det.finalize_sequence("user-1", corr_id)
        patterns = await det.get_patterns("user-1")
        assert len(patterns) <= 2

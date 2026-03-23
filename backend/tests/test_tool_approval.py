from __future__ import annotations

import asyncio

import pytest

from nobla.tools.approval import ApprovalManager
from nobla.tools.models import ApprovalRequest, ApprovalStatus


class FakeConnectionManager:
    """Mock ConnectionManager that captures sent messages."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send_to(self, connection_id: str, message: dict) -> None:
        self.sent.append((connection_id, message))


class TestApprovalManager:
    @pytest.fixture
    def fake_cm(self):
        return FakeConnectionManager()

    @pytest.fixture
    def approval_mgr(self, fake_cm):
        return ApprovalManager(connection_manager=fake_cm)

    @pytest.fixture
    def sample_request(self):
        return ApprovalRequest(
            request_id="req-001",
            tool_name="mouse.click",
            description="Click at (100, 200)",
            params_summary={"x": 100, "y": 200},
            timeout_seconds=2,
        )

    async def test_approval_approved(self, approval_mgr, sample_request, fake_cm):
        async def approve_soon():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=True)

        asyncio.create_task(approve_soon())
        status = await approval_mgr.request_approval(sample_request, "conn-1")

        assert status == ApprovalStatus.APPROVED
        assert len(fake_cm.sent) == 1
        conn_id, msg = fake_cm.sent[0]
        assert conn_id == "conn-1"
        assert msg["method"] == "tool.approval_request"
        assert msg["params"]["request_id"] == "req-001"

    async def test_approval_denied(self, approval_mgr, sample_request):
        async def deny_soon():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=False)

        asyncio.create_task(deny_soon())
        status = await approval_mgr.request_approval(sample_request, "conn-1")
        assert status == ApprovalStatus.DENIED

    async def test_approval_timeout(self, approval_mgr, sample_request):
        sample_request.timeout_seconds = 0.1
        status = await approval_mgr.request_approval(sample_request, "conn-1")
        assert status == ApprovalStatus.TIMED_OUT

    async def test_resolve_unknown_request_is_noop(self, approval_mgr):
        approval_mgr.resolve("nonexistent", approved=True)  # Should not raise

    async def test_resolve_after_timeout_is_noop(self, approval_mgr, sample_request):
        sample_request.timeout_seconds = 0.05
        await approval_mgr.request_approval(sample_request, "conn-1")
        # Now try resolving after timeout
        approval_mgr.resolve("req-001", approved=True)  # Should not raise

    async def test_deny_all(self, approval_mgr, fake_cm):
        req1 = ApprovalRequest(
            request_id="r1", tool_name="t1",
            description="d1", params_summary={}, timeout_seconds=10,
        )
        req2 = ApprovalRequest(
            request_id="r2", tool_name="t2",
            description="d2", params_summary={}, timeout_seconds=10,
        )

        async def deny_all_soon():
            await asyncio.sleep(0.05)
            approval_mgr.deny_all()

        asyncio.create_task(deny_all_soon())

        results = await asyncio.gather(
            approval_mgr.request_approval(req1, "c1"),
            approval_mgr.request_approval(req2, "c2"),
        )
        assert results[0] == ApprovalStatus.DENIED
        assert results[1] == ApprovalStatus.DENIED

    async def test_cleanup_after_resolve(self, approval_mgr, sample_request):
        async def approve():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=True)

        asyncio.create_task(approve())
        await approval_mgr.request_approval(sample_request, "conn-1")
        assert "req-001" not in approval_mgr._pending

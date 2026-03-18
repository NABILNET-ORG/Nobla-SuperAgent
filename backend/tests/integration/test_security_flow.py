from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestSecurityFlow:
    async def test_escalation_to_standard(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("system.escalate", {"tier": 2})
        assert result["tier"] == 2

    async def test_de_escalation(self, authenticated_client: RpcClient):
        await authenticated_client.call_expect_result("system.escalate", {"tier": 2})
        result = await authenticated_client.call_expect_result("system.escalate", {"tier": 1})
        assert result["tier"] == 1

    async def test_kill_switch_flow(self, authenticated_client: RpcClient):
        kill_result = await authenticated_client.call_expect_result("system.kill")
        assert kill_result["state"] in ("soft_killing", "killed")

        resp = await authenticated_client.call("chat.send", {"message": "test"})
        assert "error" in resp
        assert resp["error"]["code"] == -32030

        resume_result = await authenticated_client.call_expect_result("system.resume")
        assert resume_result["state"] == "running"

        health = await authenticated_client.call_expect_result("system.health")
        assert health["status"] == "ok"

    async def test_cost_dashboard(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("system.costs")
        assert "session_usd" in result
        assert "limits" in result
        assert "warnings" in result

from __future__ import annotations

import asyncio
import json
import os
import pytest
import websockets

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws")


class RpcClient:
    """Simple JSON-RPC 2.0 WebSocket client for integration tests."""

    def __init__(self, ws):
        self._ws = ws
        self._next_id = 1

    async def call(self, method: str, params: dict | None = None) -> dict:
        req_id = self._next_id
        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id,
        }
        await self._ws.send(json.dumps(request))
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        return json.loads(raw)

    async def call_expect_result(self, method: str, params: dict | None = None) -> dict:
        resp = await self.call(method, params)
        assert "result" in resp, f"Expected result, got: {resp}"
        return resp["result"]

    async def call_expect_error(self, method: str, params: dict | None = None) -> dict:
        resp = await self.call(method, params)
        assert "error" in resp, f"Expected error, got: {resp}"
        return resp["error"]


@pytest.fixture
async def ws_client():
    async with websockets.connect(BACKEND_WS_URL) as ws:
        yield RpcClient(ws)


@pytest.fixture
async def authenticated_client(ws_client: RpcClient):
    result = await ws_client.call_expect_result("system.register", {
        "passphrase": "integration-test-passphrase-12345",
        "display_name": "Integration Test User",
    })
    assert "user_id" in result
    return ws_client

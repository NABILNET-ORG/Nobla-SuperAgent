from __future__ import annotations

import asyncio
import json
import os
import pytest
import websockets

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws")


async def create_authenticated_client():
    ws = await websockets.connect(BACKEND_WS_URL)
    register_req = {
        "jsonrpc": "2.0",
        "method": "system.register",
        "params": {"passphrase": f"concurrent-test-{id(ws)}", "display_name": "Concurrent User"},
        "id": 1,
    }
    await ws.send(json.dumps(register_req))
    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    assert "result" in resp
    return ws


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrentConnections:
    async def test_multiple_clients_simultaneous(self):
        clients = await asyncio.gather(*[create_authenticated_client() for _ in range(3)])
        try:
            for i, ws in enumerate(clients):
                req = {"jsonrpc": "2.0", "method": "system.health", "id": 100 + i}
                await ws.send(json.dumps(req))
            for ws in clients:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                resp = json.loads(raw)
                assert "result" in resp
                assert resp["result"]["status"] == "ok"
        finally:
            for ws in clients:
                await ws.close()

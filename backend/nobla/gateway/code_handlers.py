"""Code execution RPC handlers (extracted from websocket.py)."""
from __future__ import annotations

from nobla.gateway.websocket import (
    ConnectionState,
    get_permission_checker,
    get_sandbox_manager,
    rpc_method,
)
from nobla.security.permissions import Tier


@rpc_method("code.execute")
async def handle_code_execute(params: dict, state: ConnectionState) -> dict:
    """Execute code in sandbox. Will delegate to tool platform when available."""
    pc = get_permission_checker()
    if pc:
        pc.check(current_tier=Tier(state.tier), required_tier=Tier.STANDARD)

    sm = get_sandbox_manager()
    if not sm:
        return {"error": "Sandbox not initialized"}

    code = params.get("code", "")
    language = params.get("language", "python")
    timeout = params.get("timeout")

    result = await sm.execute(code=code, language=language, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
        "timed_out": result.timed_out,
    }

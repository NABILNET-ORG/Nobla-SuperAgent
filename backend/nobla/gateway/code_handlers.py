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
    """Execute code — delegates to tool platform when available."""
    from nobla.gateway.tool_handlers import get_tool_executor

    executor = get_tool_executor()
    if executor:
        from dataclasses import asdict

        from nobla.tools.models import ToolParams

        tool_params = ToolParams(
            args={
                "code": params.get("code", ""),
                "language": params.get("language", "python"),
                "timeout": params.get("timeout"),
            },
            connection_state=state,
        )
        result = await executor.execute("code.run", tool_params)
        return asdict(result)

    # Fallback: direct sandbox execution (pre-tool-platform)
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

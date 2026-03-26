"""Phase 4D: ssh.exec — Remote command execution.

Single action: run. Conditional approval based on safe_commands list
and chaining operator detection.
"""

from __future__ import annotations

import asyncio
import time

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import (
    RemoteControlError,
    RemoteControlGuard,
    _parse_first_token,
    _has_chaining_operators,
)

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- output helpers ----


def _truncate_output(
    text: str, max_bytes: int, max_lines: int
) -> tuple[str, bool]:
    """Truncate text by byte or line count. Returns (text, was_truncated)."""
    truncated = False
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        text = "\n".join(lines)
        truncated = True
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    return text, truncated


# ---- tool ----


@register_tool
class SSHExecTool(BaseTool):
    """Execute commands on remote hosts via SSH."""

    name = "ssh.exec"
    description = "Execute a command on a remote host via an active SSH connection"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        command = params.args.get("command", "")
        rc = self._settings().remote_control

        if _has_chaining_operators(command):
            return True

        first_token = _parse_first_token(command)
        if first_token in rc.safe_commands:
            return False

        return True

    async def validate(self, params: ToolParams) -> None:
        rc = self._settings().remote_control

        if not rc.enabled:
            raise ValueError("Remote control tools are disabled in settings")

        if not params.args.get("connection_id"):
            raise ValueError("connection_id is required")
        if not params.args.get("command"):
            raise ValueError("command is required")

        timeout = params.args.get("timeout")
        if timeout is not None and timeout > rc.max_command_timeout_s:
            raise ValueError(
                f"timeout ({timeout}s) exceeds max ({rc.max_command_timeout_s}s)"
            )

        command = params.args["command"]
        try:
            RemoteControlGuard.check("command", rc, command=command)
        except RemoteControlError as exc:
            raise ValueError(f"Command blocked: {exc}") from exc

    def describe_action(self, params: ToolParams) -> str:
        command = params.args.get("command", "?")
        cid = params.args.get("connection_id", "?")
        pool = _get_pool()
        try:
            entry = pool.get(cid)
            host = entry.host
        except KeyError:
            host = "unknown"
        short_cmd = command[:80] + ("..." if len(command) > 80 else "")
        return f"Execute on {host}: {short_cmd}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        cmd = args.get("command", "")
        return {
            "action": "run",
            "connection_id": args.get("connection_id"),
            "command": cmd[:200] + ("..." if len(cmd) > 200 else ""),
            "timeout": args.get("timeout"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        rc = self._settings().remote_control
        connection_id = params.args["connection_id"]
        command = params.args["command"]
        timeout = params.args.get("timeout", rc.default_command_timeout_s)
        timeout = min(timeout, rc.max_command_timeout_s)

        pool = _get_pool()
        try:
            entry = pool.get(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        start = time.time()
        try:
            result = await asyncio.wait_for(
                entry.conn.run(command, check=False),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.time() - start) * 1000)
            return ToolResult(
                success=False,
                data={"duration_ms": elapsed, "truncated": False},
                error=f"Command timed out after {timeout}s",
            )
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SSH exec error: {exc}")

        pool.touch(connection_id)
        elapsed = int((time.time() - start) * 1000)

        stdout, stdout_trunc = _truncate_output(
            result.stdout or "", rc.max_output_bytes, rc.max_output_lines,
        )
        stderr, stderr_trunc = _truncate_output(
            result.stderr or "", rc.max_output_bytes, rc.max_output_lines,
        )

        return ToolResult(
            success=True,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.exit_status,
                "duration_ms": elapsed,
                "truncated": stdout_trunc or stderr_trunc,
            },
        )

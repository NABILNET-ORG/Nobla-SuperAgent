"""Phase 4D: ssh.connect — SSH connection lifecycle management.

Actions: connect, disconnect, list.
"""

from __future__ import annotations

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import RemoteControlError, RemoteControlGuard

_VALID_ACTIONS = {"connect", "disconnect", "list"}
_APPROVAL_ACTIONS = {"connect"}

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- lazy asyncssh import ----


def _async_connect(*args, **kwargs):
    """Wrapper for asyncssh.connect — enables mocking in tests."""
    try:
        import asyncssh
    except ImportError:
        raise RuntimeError(
            "asyncssh is not installed. Run: pip install asyncssh"
        )
    return asyncssh.connect(*args, **kwargs)


# ---- tool ----


@register_tool
class SSHConnectTool(BaseTool):
    """Manage SSH connections: connect, disconnect, list."""

    name = "ssh.connect"
    description = "SSH connection management: connect, disconnect, list active sessions"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def validate(self, params: ToolParams) -> None:
        settings = self._settings()
        rc = settings.remote_control

        if not rc.enabled:
            raise ValueError("Remote control tools are disabled in settings")

        action = params.args.get("action", "")
        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
            )

        if action == "connect":
            host = params.args.get("host")
            user = params.args.get("user")
            port = params.args.get("port", 22)

            if not host:
                raise ValueError("host is required for connect")
            if not user:
                raise ValueError("user is required for connect")
            if not isinstance(port, int) or port < 1 or port > 65535:
                raise ValueError(f"port must be 1-65535, got {port}")
            if host not in rc.allowed_hosts:
                raise ValueError(
                    f"'{host}' is not in allowed_hosts: {rc.allowed_hosts}"
                )
            if user not in rc.allowed_users:
                raise ValueError(
                    f"'{user}' is not in allowed_users: {rc.allowed_users}"
                )
            if params.args.get("password") and not rc.allow_password_auth:
                raise ValueError(
                    "password auth is disabled. Set "
                    "remote_control.allow_password_auth=true or use SSH keys."
                )

            RemoteControlGuard.check("connect", rc, host=host)

        elif action == "disconnect":
            if not params.args.get("connection_id"):
                raise ValueError("connection_id is required for disconnect")

    def describe_action(self, params: ToolParams) -> str:
        action = params.args.get("action", "")
        if action == "connect":
            host = params.args.get("host", "?")
            user = params.args.get("user", "?")
            port = params.args.get("port", 22)
            auth = "password" if params.args.get("password") else "key"
            desc = f"Connect to {user}@{host}:{port} via SSH ({auth}-based auth)"
            if auth == "password":
                desc += " — less secure, consider SSH keys"
            return desc
        if action == "disconnect":
            return f"Disconnect SSH session {params.args.get('connection_id', '?')}"
        return "List active SSH connections"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        return {
            "action": args.get("action"),
            "host": args.get("host"),
            "user": args.get("user"),
            "port": args.get("port", 22),
            "label": args.get("label"),
            "auth_method": "password" if args.get("password") else "key",
            "connection_id": args.get("connection_id"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        action = params.args["action"]
        try:
            if action == "connect":
                return await self._do_connect(params)
            elif action == "disconnect":
                return await self._do_disconnect(params)
            else:
                return self._do_list()
        except RemoteControlError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SSH error: {exc}")

    async def _do_connect(self, params: ToolParams) -> ToolResult:
        args = params.args
        host = args["host"]
        user = args["user"]
        port = args.get("port", 22)
        label = args.get("label")

        rc = self._settings().remote_control

        connect_kwargs: dict = {
            "host": host,
            "port": port,
            "username": user,
            "connect_timeout": rc.ssh_connect_timeout_s,
        }

        if args.get("password"):
            connect_kwargs["password"] = args["password"]
        elif args.get("key_path"):
            connect_kwargs["client_keys"] = [args["key_path"]]
            if args.get("passphrase"):
                connect_kwargs["passphrase"] = args["passphrase"]
        elif rc.ssh_key_path:
            connect_kwargs["client_keys"] = [rc.ssh_key_path]

        if rc.known_hosts_path:
            connect_kwargs["known_hosts"] = rc.known_hosts_path

        conn = await _async_connect(**connect_kwargs)

        pool = _get_pool()
        connection_id = pool.add(host, user, port, conn, label=label)
        RemoteControlGuard.increment_connections()

        fingerprint = ""
        try:
            raw = conn.get_extra_info("server_host_key")
            if raw:
                fingerprint = raw.hex() if isinstance(raw, bytes) else str(raw)
        except Exception:
            pass

        return ToolResult(
            success=True,
            data={
                "connection_id": connection_id,
                "host": host,
                "user": user,
                "port": port,
                "label": label,
                "host_key_fingerprint": fingerprint,
            },
        )

    async def _do_disconnect(self, params: ToolParams) -> ToolResult:
        connection_id = params.args["connection_id"]
        pool = _get_pool()
        try:
            entry = await pool.disconnect(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        RemoteControlGuard.decrement_connections()
        return ToolResult(
            success=True,
            data={"disconnected": True, "host": entry.host},
        )

    def _do_list(self) -> ToolResult:
        pool = _get_pool()
        return ToolResult(
            success=True,
            data={"connections": pool.list_connections()},
        )

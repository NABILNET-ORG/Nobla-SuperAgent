"""Phase 4D: sftp.manage — Remote file transfer via SFTP.

Actions: upload, download, list, delete, stat.
"""

from __future__ import annotations

import os
import posixpath
import stat as stat_module
import time
from pathlib import Path

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import RemoteControlError, RemoteControlGuard

_VALID_ACTIONS = {"upload", "download", "list", "delete", "stat"}
_APPROVAL_ACTIONS = {"upload", "delete"}

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- remote path validation ----


def _validate_remote_path(
    path_str: str, allowed_dirs: list[str]
) -> str:
    """Validate remote path: must be absolute, normalised, within allowed dirs."""
    if not path_str.startswith("/"):
        raise ValueError(
            f"Remote path must be absolute (start with /), got: '{path_str}'"
        )

    normalised = posixpath.normpath(path_str)

    if not allowed_dirs:
        raise ValueError(
            "No allowed_remote_dirs configured. "
            "Set remote_control.allowed_remote_dirs in your settings."
        )

    for allowed in allowed_dirs:
        allowed_norm = posixpath.normpath(allowed)
        if normalised == allowed_norm or normalised.startswith(allowed_norm + "/"):
            return normalised

    raise ValueError(
        f"Remote path '{normalised}' is not within any allowed remote dirs: "
        f"{allowed_dirs}"
    )


def _validate_local_path(
    path_str: str, allowed_dirs: list[str], label: str
) -> Path:
    """Validate local path against ComputerControlSettings allow-lists."""
    if not allowed_dirs:
        raise ValueError(
            f"No {label} configured. "
            f"Set computer_control.{label} in your settings."
        )
    resolved = Path(path_str).resolve()
    for allowed in allowed_dirs:
        try:
            resolved.relative_to(Path(allowed).resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"Local path '{resolved}' is not within any allowed {label}: "
        f"{[str(Path(d).resolve()) for d in allowed_dirs]}"
    )


# ---- tool ----


@register_tool
class SFTPManageTool(BaseTool):
    """Remote file operations via SFTP: upload, download, list, delete, stat."""

    name = "sftp.manage"
    description = "SFTP file operations: upload, download, list, delete, stat"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        action = params.args.get("action", "")
        if action in _APPROVAL_ACTIONS:
            return True
        if action == "download":
            file_size = params.args.get("file_size", 0)
            threshold = self._settings().remote_control.sftp_approval_threshold
            return file_size > threshold
        return False

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

        if not params.args.get("connection_id"):
            raise ValueError("connection_id is required")

        _NEEDS_REMOTE_PATH = {"upload", "download", "list", "delete", "stat"}
        remote_path = params.args.get("remote_path", "")
        if action in _NEEDS_REMOTE_PATH and not remote_path:
            raise ValueError("remote_path is required for " + action)
        if remote_path:
            _validate_remote_path(remote_path, rc.allowed_remote_dirs)

        if action == "upload":
            local_path = params.args.get("local_path", "")
            if not local_path:
                raise ValueError("local_path is required for upload")
            _validate_local_path(
                local_path, settings.computer_control.allowed_read_dirs,
                "allowed_read_dirs",
            )
            local = Path(local_path)
            if local.exists():
                size = local.stat().st_size
                try:
                    RemoteControlGuard.check("transfer", rc, file_size=size)
                except RemoteControlError as exc:
                    raise ValueError(str(exc)) from exc

        elif action == "download":
            local_path = params.args.get("local_path", "")
            if not local_path:
                raise ValueError("local_path is required for download")
            _validate_local_path(
                local_path, settings.computer_control.allowed_write_dirs,
                "allowed_write_dirs",
            )

    def describe_action(self, params: ToolParams) -> str:
        action = params.args.get("action", "")
        cid = params.args.get("connection_id", "?")
        pool = _get_pool()
        try:
            entry = pool.get(cid)
            host = entry.host
        except KeyError:
            host = "unknown"

        remote = params.args.get("remote_path", "?")
        if action == "upload":
            local = params.args.get("local_path", "?")
            return f"Upload {os.path.basename(local)} to {host}:{remote}"
        if action == "download":
            return f"Download {host}:{remote}"
        if action == "delete":
            return f"Delete {host}:{remote}"
        if action == "list":
            return f"List {host}:{remote}"
        return f"Stat {host}:{remote}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        return {
            "action": args.get("action"),
            "connection_id": args.get("connection_id"),
            "local_path": args.get("local_path"),
            "remote_path": args.get("remote_path"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        action = params.args["action"]
        connection_id = params.args["connection_id"]

        pool = _get_pool()
        try:
            entry = pool.get(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        try:
            sftp = await entry.conn.start_sftp_client()

            if action == "upload":
                return await self._do_upload(sftp, params, pool, connection_id)
            elif action == "download":
                return await self._do_download(sftp, params, pool, connection_id)
            elif action == "list":
                return await self._do_list(sftp, params, pool, connection_id)
            elif action == "delete":
                return await self._do_delete(sftp, params, pool, connection_id)
            else:
                return await self._do_stat(sftp, params, pool, connection_id)
        except RemoteControlError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SFTP error: {exc}")

    async def _do_upload(self, sftp, params, pool, cid) -> ToolResult:
        local_path = params.args["local_path"]
        remote_path = params.args["remote_path"]
        start = time.time()
        await sftp.put(local_path, remote_path)
        pool.touch(cid)
        elapsed = int((time.time() - start) * 1000)
        size = Path(local_path).stat().st_size
        return ToolResult(
            success=True,
            data={
                "uploaded": True,
                "local_path": local_path,
                "remote_path": remote_path,
                "size": size,
                "duration_ms": elapsed,
            },
        )

    async def _do_download(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        local_path = params.args["local_path"]
        start = time.time()
        await sftp.get(remote_path, local_path)
        pool.touch(cid)
        elapsed = int((time.time() - start) * 1000)
        size = Path(local_path).stat().st_size
        return ToolResult(
            success=True,
            data={
                "downloaded": True,
                "remote_path": remote_path,
                "local_path": local_path,
                "size": size,
                "duration_ms": elapsed,
            },
        )

    async def _do_list(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        entries_raw = await sftp.readdir(remote_path)
        pool.touch(cid)
        entries = []
        for e in entries_raw:
            attrs = e.attrs
            entries.append({
                "name": e.filename,
                "size": getattr(attrs, "size", 0),
                "modified": getattr(attrs, "mtime", 0),
                "permissions": oct(getattr(attrs, "permissions", 0)),
                "is_dir": stat_module.S_ISDIR(getattr(attrs, "permissions", 0)),
            })
        return ToolResult(
            success=True,
            data={"entries": entries, "path": remote_path},
        )

    async def _do_delete(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        await sftp.remove(remote_path)
        pool.touch(cid)
        return ToolResult(
            success=True,
            data={"deleted": True, "path": remote_path},
        )

    async def _do_stat(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        attrs = await sftp.stat(remote_path)
        pool.touch(cid)
        return ToolResult(
            success=True,
            data={
                "path": remote_path,
                "size": getattr(attrs, "size", 0),
                "modified": getattr(attrs, "mtime", 0),
                "permissions": oct(getattr(attrs, "permissions", 0)),
                "is_dir": stat_module.S_ISDIR(getattr(attrs, "permissions", 0)),
                "uid": getattr(attrs, "uid", None),
                "gid": getattr(attrs, "gid", None),
            },
        )

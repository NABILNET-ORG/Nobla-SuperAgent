"""FileManageTool — secure file operations with directory allow-lists and backups.

7 subcommands: read, write, list, move, copy, delete, info

Security model:
- Paths are resolved to absolute via Path.resolve() (kills ../ and symlink escape).
- Every path is checked against allowed_read_dirs or allowed_write_dirs.
- Empty allow-lists raise ValueError with a configuration hint.
- File size is checked for reads against max_file_size_bytes.
- Destructive ops (write, delete, move) create backups in .nobla-backup/.
- All I/O runs via asyncio.to_thread() to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from nobla.config.settings import ComputerControlSettings, Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.control.safety import ToolExecutionError
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_ACTIONS = {"read", "write", "list", "move", "copy", "delete", "info"}
_READ_ACTIONS = {"read", "list", "info"}
_WRITE_ACTIONS = {"write", "delete", "move", "copy"}
_APPROVAL_ACTIONS = {"write", "delete", "move", "copy"}

# Lazy settings cache
_settings_cache: ComputerControlSettings | None = None


def _get_settings() -> ComputerControlSettings:
    """Return (and cache) the ComputerControlSettings singleton."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings().computer_control
    return _settings_cache


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def _resolve_and_validate(
    path_str: str,
    allowed_dirs: list[str],
    label: str,
) -> Path:
    """Resolve *path_str* to absolute and verify it lives under an allowed dir.

    Raises ``ValueError`` if the allow-list is empty or the path escapes it.
    """
    if not allowed_dirs:
        raise ValueError(
            f"No {label} configured. "
            f"Set computer_control.{label} in your settings."
        )

    resolved = Path(path_str).resolve()

    for allowed in allowed_dirs:
        allowed_resolved = Path(allowed).resolve()
        try:
            resolved.relative_to(allowed_resolved)
            return resolved
        except ValueError:
            continue

    raise ValueError(
        f"Path '{resolved}' is not within any allowed {label}: "
        f"{[str(Path(d).resolve()) for d in allowed_dirs]}"
    )


# ---------------------------------------------------------------------------
# Backup management
# ---------------------------------------------------------------------------


def _create_backup(file_path: Path, max_backups: int) -> Path | None:
    """Create a timestamped backup in .nobla-backup/ and prune old ones.

    Returns the backup path, or None if the source file does not exist.
    """
    if not file_path.exists():
        return None

    backup_dir = file_path.parent / ".nobla-backup"
    backup_dir.mkdir(exist_ok=True)

    timestamp = int(time.time() * 1000)
    backup_name = f"{file_path.name}.{timestamp}"
    backup_path = backup_dir / backup_name
    shutil.copy2(file_path, backup_path)

    # Prune: keep only the newest max_backups
    pattern = f"{file_path.name}.*"
    backups = sorted(
        backup_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
    )
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        oldest.unlink(missing_ok=True)

    return backup_path


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@register_tool
class FileManageTool(BaseTool):
    """Manage files on the host filesystem with security and backups."""

    name = "file.manage"
    description = (
        "Manage files: read, write, list, move, copy, delete, info "
        "(with directory allow-lists and automatic backups)"
    )
    category = ToolCategory.FILE_SYSTEM
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional — overridden by needs_approval()

    # Injected by tests; None means use global settings.
    _settings_override: ComputerControlSettings | None = None

    def _settings(self) -> ComputerControlSettings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    # -- conditional approval -----------------------------------------------

    def needs_approval(self, params: ToolParams) -> bool:
        """Write/delete/move/copy require user approval; read/list/info do not."""
        return params.args.get("action") in _APPROVAL_ACTIONS

    # -- validation ---------------------------------------------------------

    async def validate(self, params: ToolParams) -> None:
        """Validate action name and path security."""
        args = params.args
        action = args.get("action", "")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. "
                f"Valid: {sorted(_VALID_ACTIONS)}"
            )

        settings = self._settings()
        path_str = args.get("path", "")

        if action in _READ_ACTIONS:
            resolved = _resolve_and_validate(
                path_str, settings.allowed_read_dirs, "allowed_read_dirs",
            )
            # File size check for read action
            if action == "read" and resolved.is_file():
                size = resolved.stat().st_size
                if size > settings.max_file_size_bytes:
                    raise ValueError(
                        f"File size ({size} bytes) exceeds maximum "
                        f"({settings.max_file_size_bytes} bytes)"
                    )

        elif action in ("write", "delete"):
            _resolve_and_validate(
                path_str, settings.allowed_write_dirs, "allowed_write_dirs",
            )

        elif action in ("move", "copy"):
            # Source must be readable, destination must be writable
            _resolve_and_validate(
                path_str, settings.allowed_read_dirs, "allowed_read_dirs",
            )
            dst = args.get("destination", "")
            _resolve_and_validate(
                dst, settings.allowed_write_dirs, "allowed_write_dirs",
            )

    # -- execution ----------------------------------------------------------

    async def execute(self, params: ToolParams) -> ToolResult:
        """Dispatch to the appropriate file action."""
        args = params.args
        action = args["action"]
        settings = self._settings()

        try:
            data = await asyncio.to_thread(
                self._execute_action, action, args, settings,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except PermissionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except OSError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        return ToolResult(success=True, data=data)

    def _execute_action(
        self,
        action: str,
        args: dict,
        settings: ComputerControlSettings,
    ) -> dict:
        """Synchronous dispatch — runs inside asyncio.to_thread."""
        path = Path(args["path"]).resolve()

        if action == "read":
            return self._do_read(path)

        if action == "write":
            return self._do_write(path, args, settings)

        if action == "list":
            return self._do_list(path)

        if action == "move":
            return self._do_move(path, args, settings)

        if action == "copy":
            return self._do_copy(path, args)

        if action == "delete":
            return self._do_delete(path, settings)

        if action == "info":
            return self._do_info(path)

        return {"error": f"Unknown action: {action}"}

    # -- individual actions -------------------------------------------------

    @staticmethod
    def _do_read(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        content = path.read_text(encoding="utf-8")
        return {"action": "read", "path": str(path), "content": content}

    @staticmethod
    def _do_write(
        path: Path, args: dict, settings: ComputerControlSettings,
    ) -> dict:
        # Backup existing file before overwriting
        if path.exists():
            _create_backup(path, settings.max_backups_per_file)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        content = args.get("content", "")
        path.write_text(content, encoding="utf-8")
        return {
            "action": "write",
            "path": str(path),
            "bytes_written": len(content.encode("utf-8")),
        }

    @staticmethod
    def _do_list(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        entries = []
        for child in sorted(path.iterdir()):
            try:
                stat = child.stat()
                entries.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc,
                    ).isoformat(),
                })
            except OSError:
                entries.append({
                    "name": child.name,
                    "is_dir": False,
                    "size": 0,
                    "modified": None,
                })

        return {"action": "list", "path": str(path), "entries": entries}

    @staticmethod
    def _do_move(
        path: Path, args: dict, settings: ComputerControlSettings,
    ) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {path}")
        dst = Path(args["destination"]).resolve()

        # Backup destination if it will be overwritten
        if dst.exists():
            _create_backup(dst, settings.max_backups_per_file)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dst))
        return {
            "action": "move",
            "source": str(path),
            "destination": str(dst),
        }

    @staticmethod
    def _do_copy(path: Path, args: dict) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {path}")
        dst = Path(args["destination"]).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(dst))
        return {
            "action": "copy",
            "source": str(path),
            "destination": str(dst),
        }

    @staticmethod
    def _do_delete(path: Path, settings: ComputerControlSettings) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        _create_backup(path, settings.max_backups_per_file)
        path.unlink()
        return {"action": "delete", "path": str(path)}

    @staticmethod
    def _do_info(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        stat = path.stat()
        return {
            "action": "info",
            "path": str(path),
            "size": stat.st_size,
            "is_dir": path.is_dir(),
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc,
            ).isoformat(),
            "permissions": oct(stat.st_mode),
        }

    # -- display helpers ----------------------------------------------------

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        args = params.args
        action = args.get("action", "unknown")
        path = args.get("path", "")

        if action == "read":
            return f"Read file: {path}"
        if action == "write":
            return f"Write file: {path}"
        if action == "list":
            return f"List directory: {path}"
        if action == "move":
            return f"Move {path} -> {args.get('destination', '?')}"
        if action == "copy":
            return f"Copy {path} -> {args.get('destination', '?')}"
        if action == "delete":
            return f"Delete file: {path}"
        if action == "info":
            return f"Get info: {path}"
        return f"File {action}: {path}"

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display — exposes only safe fields."""
        args = params.args
        summary: dict = {"action": args.get("action", "")}

        if "path" in args:
            summary["path"] = args["path"]
        if "destination" in args:
            summary["destination"] = args["destination"]
        # Intentionally omit "content" — could be large or sensitive

        return summary

"""Phase 4D: Safety guard for remote control operations.

Mirrors InputSafetyGuard from Phase 4B with SSH-specific checks:
halt/resume, host allow-list, connection caps, blocked commands, file size.
"""

from __future__ import annotations

import re
import shlex

from nobla.config.settings import RemoteControlSettings


class RemoteControlError(Exception):
    """Raised when a remote-control safety check fails."""


class RemoteControlGuard:
    """Singleton safety checks for SSH/SFTP operations.

    All methods are classmethods — no instance needed.
    """

    _halted: bool = False
    _active_connection_count: int = 0

    # ---- public API ----

    @classmethod
    def check(
        cls,
        operation: str,
        settings: RemoteControlSettings,
        **kwargs: object,
    ) -> None:
        """Unified safety check entry point.

        Args:
            operation: "connect", "command", or "transfer"
            settings: RemoteControlSettings instance
            **kwargs:
                connect  → host: str
                command  → command: str
                transfer → file_size: int
        """
        cls._check_halt()

        if operation == "connect":
            cls._check_host_allowed(str(kwargs["host"]), settings)
            cls._check_connection_cap(settings)
        elif operation == "command":
            cls._check_blocked_binary(str(kwargs["command"]), settings)
            cls._check_blocked_pattern(str(kwargs["command"]), settings)
        elif operation == "transfer":
            cls._check_file_size(int(kwargs["file_size"]), settings)

    @classmethod
    def halt(cls) -> None:
        """Emergency stop."""
        cls._halted = True

    @classmethod
    def resume(cls) -> None:
        """Clear halt flag."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Wipe all state (tests)."""
        cls._halted = False
        cls._active_connection_count = 0

    @classmethod
    def increment_connections(cls) -> None:
        cls._active_connection_count += 1

    @classmethod
    def decrement_connections(cls) -> None:
        cls._active_connection_count = max(0, cls._active_connection_count - 1)

    # ---- internal checks ----

    @classmethod
    def _check_halt(cls) -> None:
        if cls._halted:
            raise RemoteControlError(
                "Remote control is halted. Call resume() to re-enable."
            )

    @classmethod
    def _check_host_allowed(cls, host: str, settings: RemoteControlSettings) -> None:
        if not settings.allowed_hosts:
            raise RemoteControlError(
                "No allowed_hosts configured. "
                "Set remote_control.allowed_hosts in your settings."
            )
        if host not in settings.allowed_hosts:
            raise RemoteControlError(
                f"Host '{host}' is not in allowed_hosts: {settings.allowed_hosts}"
            )

    @classmethod
    def _check_connection_cap(cls, settings: RemoteControlSettings) -> None:
        if cls._active_connection_count >= settings.max_connections:
            raise RemoteControlError(
                f"Max connections ({settings.max_connections}) reached. "
                "Disconnect an existing session first."
            )

    @classmethod
    def _check_blocked_binary(
        cls, command: str, settings: RemoteControlSettings
    ) -> None:
        first_token = _parse_first_token(command)
        if first_token in settings.blocked_binaries:
            raise RemoteControlError(
                f"Command blocked: '{first_token}' is in blocked_binaries"
            )

    @classmethod
    def _check_blocked_pattern(
        cls, command: str, settings: RemoteControlSettings
    ) -> None:
        for pattern in settings.blocked_patterns:
            if re.search(pattern, command):
                raise RemoteControlError(
                    f"Command blocked: matches blocked pattern '{pattern}'"
                )

    @classmethod
    def _check_file_size(
        cls, file_size: int, settings: RemoteControlSettings
    ) -> None:
        if file_size > settings.sftp_max_file_size:
            raise RemoteControlError(
                f"File size {file_size} exceeds limit "
                f"({settings.sftp_max_file_size} bytes)"
            )


# ---- module-level helpers ----

_CHAINING_OPERATORS = {";", "&&", "||", "|", "`", "$(", "\n", "<<", "<("}


def _parse_first_token(command: str) -> str:
    """Extract the first command token (basename), ignoring env prefixes."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""
    for token in tokens:
        if "=" not in token:
            return token.split("/")[-1]
    return ""


def _has_chaining_operators(command: str) -> bool:
    """Check if *command* chains multiple operations."""
    return any(op in command for op in _CHAINING_OPERATORS)

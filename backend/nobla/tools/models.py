"""Data models for the Nobla tool platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nobla.gateway.websocket import ConnectionState


class ToolCategory(str, Enum):
    """Categories for organizing tools."""

    VISION = "vision"
    INPUT = "input"
    FILE_SYSTEM = "file_system"
    APP_CONTROL = "app_control"
    CODE = "code"
    GIT = "git"
    SSH = "ssh"
    CLIPBOARD = "clipboard"
    SEARCH = "search"
    SKILL = "skill"  # Catch-all for marketplace skill categories


class ApprovalStatus(str, Enum):
    """Status of a user approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass
class ToolParams:
    """Input parameters passed to a tool's execute method."""

    args: dict[str, Any]
    connection_state: ConnectionState
    context: dict[str, Any] | None = None


@dataclass
class ToolResult:
    """Uniform result returned by every tool."""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    approval_was_required: bool = False


@dataclass
class ApprovalRequest:
    """Request sent to Flutter for user approval of a tool action."""

    request_id: str
    tool_name: str
    description: str
    params_summary: dict
    screenshot_b64: str | None = None
    timeout_seconds: int = 30
    status: ApprovalStatus = field(default=ApprovalStatus.PENDING)

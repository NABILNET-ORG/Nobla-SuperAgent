"""Data models for the multi-agent system (Phase 6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from nobla.security.permissions import Tier


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IsolationLevel(str, Enum):
    FULL_ISOLATED = "full_isolated"
    SHARED_READ = "shared_read"
    SHARED_READWRITE = "shared_readwrite"


class MessageType(str, Enum):
    TASK_ASSIGN = "task_assign"
    TASK_UPDATE = "task_update"
    TASK_RESULT = "task_result"
    TASK_ERROR = "task_error"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"


class ResourceLimits(BaseModel):
    max_tool_calls: int = 50
    max_llm_tokens: int = 100_000
    max_memory_writes: int = 200
    max_runtime_seconds: int = 600


class WorkspaceConfig(BaseModel):
    isolation: IsolationLevel = IsolationLevel.FULL_ISOLATED
    tool_whitelist: list[str] = Field(default_factory=list)
    shared_pools: list[str] = Field(default_factory=list)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)


class AgentConfig(BaseModel):
    name: str
    description: str
    role: str
    tier: Tier = Tier.STANDARD
    llm_tier: str = "balanced"
    allowed_tools: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    max_concurrent_tasks: int = 3
    default_isolation: IsolationLevel = IsolationLevel.FULL_ISOLATED
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)


class AgentTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str | None = None
    workflow_id: str
    assigner: str
    assignee: str
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: datetime | None = None
    retry_count: int = 0


class AgentMessage(BaseModel):
    message_type: MessageType
    sender: str
    recipient: str
    task: AgentTask | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(slots=True)
class WorkflowState:
    """Mutable workflow state — uses @dataclass intentionally:
    frequently mutated in-place, no validation needed, lighter weight.
    Matches NoblaEvent and ChannelMessage pattern."""

    workflow_id: str
    user_id: str
    user_tier: Tier
    instruction: str
    task_graph: dict[str, AgentTask]
    agent_assignments: dict[str, str]
    status: str
    depth: int
    created_at: datetime

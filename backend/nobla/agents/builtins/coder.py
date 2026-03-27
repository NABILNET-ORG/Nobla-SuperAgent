"""CoderAgent — reference implementation for code tasks (Phase 6)."""

from __future__ import annotations

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig, AgentStatus, AgentTask, IsolationLevel, TaskStatus
from nobla.security.permissions import Tier

CODER_CONFIG = AgentConfig(
    name="coder",
    description="Generates code, debugs issues, reviews code, and performs git operations.",
    role=(
        "You are a coding assistant. Given a coding task, generate clean, "
        "well-structured code with appropriate error handling. For debugging "
        "tasks, analyze the problem and provide a fix."
    ),
    tier=Tier.ELEVATED,
    llm_tier="strong",
    allowed_tools=[],  # Populated at registration time from actual tool registry
    default_isolation=IsolationLevel.SHARED_READ,
)


class CoderAgent(BaseAgent):
    """Reference agent: code generation, debugging, review."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        self.status = AgentStatus.BUSY
        try:
            response = await self.think(
                f"{self.role}\n\nTask: {task.instruction}"
            )
            task.artifacts.append({
                "type": "code",
                "content": response,
            })
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.artifacts.append({"type": "error", "content": str(e)})
        return task

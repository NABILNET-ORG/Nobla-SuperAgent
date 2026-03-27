"""ResearcherAgent — reference implementation for research tasks (Phase 6)."""

from __future__ import annotations

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig, AgentStatus, AgentTask, IsolationLevel, TaskStatus
from nobla.security.permissions import Tier

RESEARCHER_CONFIG = AgentConfig(
    name="researcher",
    description="Searches the web, analyzes documents, extracts information, and summarizes findings.",
    role=(
        "You are a research assistant. Given a research question or topic, "
        "search for relevant information, extract key findings, and provide "
        "a clear, concise summary with sources."
    ),
    tier=Tier.STANDARD,
    llm_tier="balanced",
    allowed_tools=[],  # Populated at registration time from actual tool registry
    default_isolation=IsolationLevel.SHARED_READWRITE,
)


class ResearcherAgent(BaseAgent):
    """Reference agent: research, search, summarize."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        self.status = AgentStatus.BUSY
        try:
            response = await self.think(
                f"{self.role}\n\nTask: {task.instruction}"
            )
            task.artifacts.append({
                "type": "research",
                "content": response,
            })
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.artifacts.append({"type": "error", "content": str(e)})
        return task

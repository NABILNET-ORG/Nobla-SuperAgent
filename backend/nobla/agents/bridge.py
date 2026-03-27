"""AgentToolBridge — expose an agent as a BaseTool (Phase 6).

Follows SkillToolBridge pattern: wraps agent config so the orchestrator
can be invoked through the standard ToolExecutor pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolResult

if TYPE_CHECKING:
    from nobla.agents.models import AgentConfig
    from nobla.agents.orchestrator import AgentOrchestrator
    from nobla.tools.models import ToolParams


class AgentToolBridge(BaseTool):
    """Wraps an agent type as a BaseTool for the tool platform."""

    def __init__(
        self, config: AgentConfig, orchestrator: AgentOrchestrator,
    ) -> None:
        self._agent_config = config
        self._orchestrator = orchestrator
        self.name = f"agent.{config.name}"
        self.description = config.description
        self.category = ToolCategory.AGENT
        self.tier = config.tier
        self.requires_approval = config.requires_approval

    async def execute(self, params: ToolParams) -> ToolResult:
        instruction = params.args.get("instruction", "")
        user_id = params.connection_state.user_id
        user_tier = params.connection_state.tier

        try:
            workflow = await self._orchestrator.run_workflow(
                instruction=instruction,
                user_id=user_id or "unknown",
                user_tier=user_tier,
                agent_team=[self._agent_config.name],
            )
            artifacts = []
            for task in workflow.task_graph.values():
                artifacts.extend(task.artifacts)

            return ToolResult(
                success=workflow.status == "completed",
                data={"artifacts": artifacts, "workflow_id": workflow.workflow_id},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

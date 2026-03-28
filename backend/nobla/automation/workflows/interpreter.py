"""NL Workflow Interpreter — parse natural language into workflows (Phase 6).

Architecture:
    WorkflowInterpreter takes a natural language description and produces
    a Workflow with steps, triggers, and nl_source fragments.  Uses LLM
    when available, falls back to heuristic keyword parsing.

    LLM prompt asks for JSON with:
        - triggers: [{event_pattern, conditions: [{field, op, value}]}]
        - steps: [{id, name, type, config, depends_on, nl_source}]

    Two-pass id resolution: first pass creates steps (maps LLM short ids
    like "s1" to real UUIDs), second pass resolves depends_on refs.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any

from nobla.automation.workflows.models import (
    ConditionOperator,
    ErrorHandling,
    StepType,
    TriggerCondition,
    Workflow,
    WorkflowStep,
    WorkflowTrigger,
)

if TYPE_CHECKING:
    from nobla.brain.router import LLMRouter

logger = logging.getLogger(__name__)

WORKFLOW_PROMPT = """You are a workflow builder. Given a natural language description,
produce a JSON workflow with triggers and steps.

Return ONLY valid JSON with this structure:
{{
  "triggers": [
    {{
      "event_pattern": "webhook.github.*",
      "conditions": [{{"field": "payload.branch", "op": "eq", "value": "main"}}]
    }}
  ],
  "steps": [
    {{
      "id": "s1",
      "name": "Step name",
      "type": "tool|agent|condition|webhook|delay|approval",
      "config": {{}},
      "depends_on": [],
      "nl_source": "the part of user text this step came from"
    }}
  ]
}}

Valid step types: tool, agent, condition, webhook, delay, approval.
Valid condition operators: eq, neq, gt, lt, gte, lte, contains, exists.

For condition steps, config must have "branches" array:
{{"branches": [{{"name": "branch_name", "condition": {{"field": "...", "op": "eq", "value": ...}}, "next_steps": ["s3"]}}], "default_branch": "branch_name"}}

Trigger event_pattern uses fnmatch wildcards (e.g. "webhook.github.*", "scheduler.task.*").
Triggers with "every" or "at" time expressions should use event_pattern "scheduler.cron.*".
Manual triggers use event_pattern "manual.*".

If no clear trigger, use "manual.*" as the event_pattern.

User description: {description}"""


class WorkflowInterpreter:
    """Parses natural language into Workflow definitions.

    Args:
        router: LLMRouter for LLM-based parsing (optional).
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router

    async def interpret(
        self, description: str, user_id: str = "", name: str = "",
    ) -> Workflow:
        """Parse a natural language workflow description.

        Tries LLM first, falls back to heuristic parsing.

        Args:
            description: Natural language workflow description.
            user_id: Owner of the workflow.
            name: Optional workflow name (auto-generated if empty).

        Returns:
            A Workflow with steps and triggers populated.
        """
        try:
            if self._router:
                return await self._llm_interpret(description, user_id, name)
        except Exception as e:
            logger.warning("llm_interpret_failed, using heuristic: %s", e)

        return self._heuristic_interpret(description, user_id, name)

    # ------------------------------------------------------------------
    # LLM-based interpretation
    # ------------------------------------------------------------------

    async def _llm_interpret(
        self, description: str, user_id: str, name: str,
    ) -> Workflow:
        """Use LLM to parse the workflow description."""
        prompt = WORKFLOW_PROMPT.format(description=description)
        response = await self._router.route(prompt, tier="balanced")

        data = json.loads(response)
        return self._parse_llm_response(data, description, user_id, name)

    def _parse_llm_response(
        self,
        data: dict[str, Any],
        description: str,
        user_id: str,
        name: str,
    ) -> Workflow:
        """Parse LLM JSON response into a Workflow."""
        workflow = Workflow(
            user_id=user_id,
            name=name or self._generate_name(description),
            description=description,
        )

        # Parse triggers
        for t_raw in data.get("triggers", []):
            conditions = []
            for c_raw in t_raw.get("conditions", []):
                conditions.append(TriggerCondition(
                    field_path=c_raw.get("field", ""),
                    operator=ConditionOperator(c_raw.get("op", "eq")),
                    value=c_raw.get("value"),
                ))
            workflow.triggers.append(WorkflowTrigger(
                workflow_id=workflow.workflow_id,
                event_pattern=t_raw.get("event_pattern", "manual.*"),
                conditions=conditions,
            ))

        # First pass: create steps, map LLM ids to real UUIDs
        id_map: dict[str, str] = {}
        steps: list[WorkflowStep] = []
        for s_raw in data.get("steps", []):
            step_id = str(uuid.uuid4())
            llm_id = s_raw.get("id", step_id)
            id_map[llm_id] = step_id

            step_type = s_raw.get("type", "tool")
            try:
                st = StepType(step_type)
            except ValueError:
                st = StepType.TOOL

            steps.append(WorkflowStep(
                step_id=step_id,
                workflow_id=workflow.workflow_id,
                name=s_raw.get("name", f"Step {llm_id}"),
                type=st,
                config=s_raw.get("config", {}),
                nl_source=s_raw.get("nl_source"),
            ))

        # Second pass: resolve depends_on refs
        for i, s_raw in enumerate(data.get("steps", [])):
            raw_deps = s_raw.get("depends_on", [])
            resolved = []
            for dep in raw_deps:
                if dep in id_map:
                    resolved.append(id_map[dep])
                else:
                    logger.warning(
                        "Unknown dependency ref '%s' in step '%s', skipping",
                        dep, s_raw.get("id", "?"),
                    )
            steps[i].depends_on = resolved

            # Also resolve next_steps in condition branches
            if steps[i].type == StepType.CONDITION:
                self._resolve_condition_refs(steps[i], id_map)

        workflow.steps = steps

        if not workflow.triggers:
            workflow.triggers.append(WorkflowTrigger(
                workflow_id=workflow.workflow_id,
                event_pattern="manual.*",
            ))

        return workflow

    @staticmethod
    def _resolve_condition_refs(
        step: WorkflowStep, id_map: dict[str, str]
    ) -> None:
        """Resolve LLM ids in condition branch next_steps to real UUIDs."""
        for branch in step.config.get("branches", []):
            resolved = []
            for ref in branch.get("next_steps", []):
                if ref in id_map:
                    resolved.append(id_map[ref])
                else:
                    resolved.append(ref)
            branch["next_steps"] = resolved

    # ------------------------------------------------------------------
    # Heuristic fallback
    # ------------------------------------------------------------------

    def _heuristic_interpret(
        self, description: str, user_id: str, name: str,
    ) -> Workflow:
        """Parse workflow from keywords when LLM is unavailable."""
        workflow = Workflow(
            user_id=user_id,
            name=name or self._generate_name(description),
            description=description,
        )

        # Extract trigger
        trigger = self._extract_trigger(description)
        workflow.triggers.append(WorkflowTrigger(
            workflow_id=workflow.workflow_id,
            event_pattern=trigger["pattern"],
            conditions=trigger["conditions"],
        ))

        # Extract steps from comma/then-separated clauses
        clauses = self._split_clauses(description)
        steps: list[WorkflowStep] = []
        prev_id: str | None = None

        for clause in clauses:
            step = self._clause_to_step(clause, workflow.workflow_id)
            if prev_id:
                step.depends_on = [prev_id]
            steps.append(step)
            prev_id = step.step_id

        workflow.steps = steps
        return workflow

    def _extract_trigger(self, description: str) -> dict[str, Any]:
        """Extract trigger info from NL description."""
        desc_lower = description.lower()
        conditions: list[TriggerCondition] = []

        # Webhook triggers
        webhook_patterns = {
            "github": "webhook.github.*",
            "gitlab": "webhook.gitlab.*",
            "stripe": "webhook.stripe.*",
            "slack": "webhook.slack.*",
        }
        for keyword, pattern in webhook_patterns.items():
            if keyword in desc_lower:
                # Look for branch conditions
                branch_match = re.search(
                    r"(?:branch|ref)\s+(?:is\s+|==\s*|=\s*)?[\"']?(\w+)[\"']?",
                    desc_lower,
                )
                if branch_match:
                    conditions.append(TriggerCondition(
                        field_path="payload.branch",
                        operator=ConditionOperator.EQ,
                        value=branch_match.group(1),
                    ))
                return {"pattern": pattern, "conditions": conditions}

        # Time-based triggers
        time_keywords = [
            "every", "daily", "weekly", "monthly", "hourly",
            "at ", "each morning", "each evening",
        ]
        for kw in time_keywords:
            if kw in desc_lower:
                return {"pattern": "scheduler.cron.*", "conditions": conditions}

        # Default: manual
        return {"pattern": "manual.*", "conditions": conditions}

    @staticmethod
    def _split_clauses(description: str) -> list[str]:
        """Split NL description into action clauses."""
        # Remove trigger prefix
        desc = re.sub(
            r"^(when|if|every|on|after)\s+[^,]+[,]\s*",
            "", description, flags=re.IGNORECASE,
        )
        # Split on "then", "and then", commas, "after that"
        parts = re.split(
            r"\s*(?:,\s*then\s+|,\s*and\s+then\s+|,\s*then\s*|"
            r"\s+then\s+|\s+and\s+then\s+|\s+after\s+that\s+|,\s*)\s*",
            desc,
        )
        return [p.strip() for p in parts if p.strip()]

    def _clause_to_step(
        self, clause: str, workflow_id: str,
    ) -> WorkflowStep:
        """Convert a single NL clause into a WorkflowStep."""
        clause_lower = clause.lower()

        # Detect step type from keywords (order matters — check more
        # specific types first to avoid "approve deployment" matching "deploy")
        if any(w in clause_lower for w in ["approve", "confirm", "review"]):
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.APPROVAL,
                config={"message": clause},
                nl_source=clause,
            )
        if any(w in clause_lower for w in ["if ", "check", "whether"]):
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.CONDITION,
                config={"branches": [], "default_branch": ""},
                nl_source=clause,
            )
        if any(w in clause_lower for w in ["test", "run", "execute", "build"]):
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.TOOL,
                config={"tool": "code.run", "description": clause},
                nl_source=clause,
            )
        if any(w in clause_lower for w in ["deploy", "release", "publish"]):
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.TOOL,
                config={"tool": "ssh.exec", "description": clause},
                nl_source=clause,
            )
        if any(w in clause_lower for w in ["notify", "send", "post", "message", "alert"]):
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.WEBHOOK,
                config={"url": "", "payload": {"message": clause}, "description": clause},
                nl_source=clause,
            )
        if any(w in clause_lower for w in ["wait", "delay", "pause"]):
            # Try to extract duration
            match = re.search(r"(\d+)\s*(second|minute|hour|sec|min|hr)", clause_lower)
            seconds = 60  # default
            if match:
                val = int(match.group(1))
                unit = match.group(2)
                if "min" in unit:
                    seconds = val * 60
                elif "hour" in unit or "hr" in unit:
                    seconds = val * 3600
                else:
                    seconds = val
            return WorkflowStep(
                workflow_id=workflow_id,
                name=clause[:60],
                type=StepType.DELAY,
                config={"seconds": seconds},
                nl_source=clause,
            )
        # Default: tool step
        return WorkflowStep(
            workflow_id=workflow_id,
            name=clause[:60],
            type=StepType.TOOL,
            config={"description": clause},
            nl_source=clause,
        )

    @staticmethod
    def _generate_name(description: str) -> str:
        """Generate a short name from a description."""
        words = description.split()[:6]
        name = " ".join(words)
        if len(description.split()) > 6:
            name += "..."
        return name

"""Template registry — bundled + user templates with search/filter (Phase 6).

Provides TemplateRegistry for managing workflow templates:
    - 5 bundled starter templates (CI/CD, backup, relay, approval, pipeline)
    - CRUD for user-submitted templates
    - Search by name/description text, category, and tags
"""

from __future__ import annotations

import logging
from typing import Any

from nobla.automation.workflows.templates import (
    TemplateCategory,
    TemplateStep,
    TemplateTrigger,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class TemplateRegistry:
    """In-memory template library with bundled defaults and search.

    Args:
        load_bundled: Whether to load built-in templates on init.
    """

    def __init__(self, load_bundled: bool = True) -> None:
        self._templates: dict[str, WorkflowTemplate] = {}
        if load_bundled:
            self._load_bundled()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, template: WorkflowTemplate) -> WorkflowTemplate:
        """Add a template to the registry.

        Raises:
            ValueError: If a template with the same ID already exists.
        """
        if template.template_id in self._templates:
            raise ValueError(
                f"Template already registered: {template.template_id}"
            )
        self._templates[template.template_id] = template
        logger.info("template_registered id=%s name=%s", template.template_id, template.name)
        return template

    def get(self, template_id: str) -> WorkflowTemplate:
        """Retrieve a template by ID.

        Raises:
            KeyError: If not found.
        """
        try:
            return self._templates[template_id]
        except KeyError:
            raise KeyError(f"Template not found: {template_id}") from None

    def delete(self, template_id: str) -> None:
        """Remove a template.

        Raises:
            KeyError: If not found.
            ValueError: If template is bundled (cannot be deleted).
        """
        tmpl = self.get(template_id)
        if tmpl.bundled:
            raise ValueError("Cannot delete bundled templates")
        del self._templates[template_id]
        logger.info("template_deleted id=%s", template_id)

    def list_all(self) -> list[WorkflowTemplate]:
        """Return all templates sorted by name."""
        return sorted(self._templates.values(), key=lambda t: t.name)

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------

    def search(
        self,
        query: str = "",
        category: TemplateCategory | None = None,
        tags: list[str] | None = None,
    ) -> list[WorkflowTemplate]:
        """Search templates by text, category, and/or tags.

        Args:
            query: Case-insensitive substring match on name + description.
            category: Filter by category.
            tags: Filter by tags (AND logic — all must be present).

        Returns:
            Matching templates sorted by name.
        """
        results = list(self._templates.values())

        if category is not None:
            results = [t for t in results if t.category == category]

        if tags:
            tag_set = set(t.lower() for t in tags)
            results = [
                t for t in results
                if tag_set.issubset(set(tg.lower() for tg in t.tags))
            ]

        if query:
            q = query.lower()
            results = [
                t for t in results
                if q in t.name.lower() or q in t.description.lower()
            ]

        return sorted(results, key=lambda t: t.name)

    def list_categories(self) -> list[dict[str, Any]]:
        """Return categories with template counts."""
        counts: dict[str, int] = {}
        for tmpl in self._templates.values():
            counts[tmpl.category.value] = counts.get(tmpl.category.value, 0) + 1
        return [
            {"category": cat.value, "label": cat.value.replace("_", " ").title(), "count": counts.get(cat.value, 0)}
            for cat in TemplateCategory
            if counts.get(cat.value, 0) > 0
        ]

    @property
    def count(self) -> int:
        """Total number of registered templates."""
        return len(self._templates)

    # ------------------------------------------------------------------
    # Bundled templates
    # ------------------------------------------------------------------

    def _load_bundled(self) -> None:
        """Load the 5 starter templates."""
        for builder in (
            _build_github_ci_notifier,
            _build_scheduled_backup,
            _build_webhook_relay,
            _build_approval_chain,
            _build_data_pipeline,
        ):
            tmpl = builder()
            self._templates[tmpl.template_id] = tmpl
        logger.info("bundled_templates_loaded count=%d", len(self._templates))


# ---------------------------------------------------------------------------
# Bundled template builders
# ---------------------------------------------------------------------------


def _build_github_ci_notifier() -> WorkflowTemplate:
    """GitHub CI Notifier — webhook → condition → notify."""
    return WorkflowTemplate(
        template_id="bundled-github-ci-notifier",
        name="GitHub CI Notifier",
        description=(
            "Receives GitHub webhook events, checks CI status, "
            "and sends notifications on pass or fail."
        ),
        category=TemplateCategory.CI_CD,
        tags=["github", "ci", "notifications", "webhook"],
        author="Nobla",
        version="1.0.0",
        icon="github",
        bundled=True,
        steps=[
            TemplateStep(
                ref_id="receive_webhook",
                name="Receive Webhook",
                type="webhook",
                config={"source": "github", "events": ["check_suite", "workflow_run"]},
                description="Receives inbound GitHub webhook events.",
            ),
            TemplateStep(
                ref_id="check_status",
                name="Check CI Status",
                type="condition",
                config={
                    "branches": [
                        {
                            "name": "passed",
                            "condition": {"field": "payload.conclusion", "op": "eq", "value": "success"},
                            "next_steps": ["notify_success"],
                        },
                        {
                            "name": "failed",
                            "condition": {"field": "payload.conclusion", "op": "neq", "value": "success"},
                            "next_steps": ["notify_failure"],
                        },
                    ],
                    "default_branch": "failed",
                },
                depends_on=["receive_webhook"],
                description="Routes based on CI pass/fail status.",
            ),
            TemplateStep(
                ref_id="notify_success",
                name="Notify Success",
                type="tool",
                config={"tool": "send_message", "message": "CI passed for {{payload.repository.full_name}}"},
                depends_on=["check_status"],
                description="Sends success notification.",
            ),
            TemplateStep(
                ref_id="notify_failure",
                name="Notify Failure",
                type="tool",
                config={"tool": "send_message", "message": "CI FAILED for {{payload.repository.full_name}}"},
                depends_on=["check_status"],
                description="Sends failure notification.",
            ),
        ],
        triggers=[
            TemplateTrigger(
                event_pattern="webhook.github.*",
                description="Fires on any GitHub webhook event.",
            ),
        ],
    )


def _build_scheduled_backup() -> WorkflowTemplate:
    """Scheduled Backup — delay → backup → check → notify."""
    return WorkflowTemplate(
        template_id="bundled-scheduled-backup",
        name="Scheduled Backup",
        description=(
            "Runs a backup task on a schedule, checks if it succeeded, "
            "and sends a webhook notification with the result."
        ),
        category=TemplateCategory.DEVOPS,
        tags=["backup", "schedule", "devops", "notifications"],
        author="Nobla",
        version="1.0.0",
        icon="backup",
        bundled=True,
        steps=[
            TemplateStep(
                ref_id="wait_schedule",
                name="Wait for Schedule",
                type="delay",
                config={"delay_seconds": 0},
                description="Placeholder for schedule trigger timing.",
            ),
            TemplateStep(
                ref_id="run_backup",
                name="Run Backup",
                type="tool",
                config={"tool": "backup", "target": "database"},
                depends_on=["wait_schedule"],
                error_handling="retry",
                max_retries=2,
                description="Executes the backup operation.",
            ),
            TemplateStep(
                ref_id="check_result",
                name="Check Result",
                type="condition",
                config={
                    "branches": [
                        {
                            "name": "success",
                            "condition": {"field": "result.status", "op": "eq", "value": "ok"},
                            "next_steps": ["notify_result"],
                        },
                        {
                            "name": "failure",
                            "condition": {"field": "result.status", "op": "neq", "value": "ok"},
                            "next_steps": ["notify_result"],
                        },
                    ],
                    "default_branch": "failure",
                },
                depends_on=["run_backup"],
                description="Checks backup success or failure.",
            ),
            TemplateStep(
                ref_id="notify_result",
                name="Notify Result",
                type="webhook",
                config={"url": "", "method": "POST"},
                depends_on=["check_result"],
                description="Sends backup result via outbound webhook.",
            ),
        ],
        triggers=[
            TemplateTrigger(
                event_pattern="schedule.daily",
                description="Fires on daily schedule.",
            ),
        ],
    )


def _build_webhook_relay() -> WorkflowTemplate:
    """Webhook Relay — receive → transform → forward."""
    return WorkflowTemplate(
        template_id="bundled-webhook-relay",
        name="Webhook Relay",
        description=(
            "Receives an inbound webhook, transforms the payload, "
            "and forwards it to another endpoint."
        ),
        category=TemplateCategory.INTEGRATION,
        tags=["webhook", "relay", "integration", "transform"],
        author="Nobla",
        version="1.0.0",
        icon="relay",
        bundled=True,
        steps=[
            TemplateStep(
                ref_id="receive_inbound",
                name="Receive Inbound",
                type="webhook",
                config={"source": "any"},
                description="Captures the inbound webhook payload.",
            ),
            TemplateStep(
                ref_id="transform_payload",
                name="Transform Payload",
                type="tool",
                config={"tool": "transform", "mapping": {}},
                depends_on=["receive_inbound"],
                description="Transforms payload to outbound format.",
            ),
            TemplateStep(
                ref_id="forward_outbound",
                name="Forward Outbound",
                type="webhook",
                config={"url": "", "method": "POST"},
                depends_on=["transform_payload"],
                error_handling="retry",
                max_retries=3,
                description="Sends transformed payload to destination.",
            ),
        ],
        triggers=[
            TemplateTrigger(
                event_pattern="webhook.inbound.*",
                description="Fires on any inbound webhook.",
            ),
        ],
    )


def _build_approval_chain() -> WorkflowTemplate:
    """Approval Chain — approval → condition → execute → notify."""
    return WorkflowTemplate(
        template_id="bundled-approval-chain",
        name="Approval Chain",
        description=(
            "Requests user approval, then executes an agent task "
            "if approved, or notifies of rejection."
        ),
        category=TemplateCategory.APPROVAL,
        tags=["approval", "agent", "notifications", "governance"],
        author="Nobla",
        version="1.0.0",
        icon="approval",
        bundled=True,
        steps=[
            TemplateStep(
                ref_id="request_approval",
                name="Request Approval",
                type="approval",
                config={"message": "Please approve the following action.", "timeout_minutes": 60},
                description="Sends approval request to designated approver.",
            ),
            TemplateStep(
                ref_id="check_approval",
                name="Check Approval",
                type="condition",
                config={
                    "branches": [
                        {
                            "name": "approved",
                            "condition": {"field": "result.approved", "op": "eq", "value": True},
                            "next_steps": ["execute_task"],
                        },
                        {
                            "name": "rejected",
                            "condition": {"field": "result.approved", "op": "eq", "value": False},
                            "next_steps": ["notify_rejection"],
                        },
                    ],
                    "default_branch": "rejected",
                },
                depends_on=["request_approval"],
                description="Routes based on approval decision.",
            ),
            TemplateStep(
                ref_id="execute_task",
                name="Execute Task",
                type="agent",
                config={"agent": "default", "task": ""},
                depends_on=["check_approval"],
                description="Runs the approved agent task.",
            ),
            TemplateStep(
                ref_id="notify_rejection",
                name="Notify Rejection",
                type="tool",
                config={"tool": "send_message", "message": "Action was rejected."},
                depends_on=["check_approval"],
                description="Notifies requester of rejection.",
            ),
        ],
        triggers=[
            TemplateTrigger(
                event_pattern="manual.trigger",
                description="Manually triggered.",
            ),
        ],
    )


def _build_data_pipeline() -> WorkflowTemplate:
    """Data Pipeline — fetch → transform → validate → store."""
    return WorkflowTemplate(
        template_id="bundled-data-pipeline",
        name="Data Pipeline",
        description=(
            "Fetches data from a source, transforms it, validates "
            "the output, and stores it in a destination."
        ),
        category=TemplateCategory.DATA_PIPELINE,
        tags=["data", "pipeline", "etl", "schedule"],
        author="Nobla",
        version="1.0.0",
        icon="pipeline",
        bundled=True,
        steps=[
            TemplateStep(
                ref_id="fetch_data",
                name="Fetch Data",
                type="tool",
                config={"tool": "fetch", "source": ""},
                error_handling="retry",
                max_retries=2,
                description="Retrieves data from the source.",
            ),
            TemplateStep(
                ref_id="transform_data",
                name="Transform Data",
                type="tool",
                config={"tool": "transform", "rules": []},
                depends_on=["fetch_data"],
                description="Applies transformation rules to the data.",
            ),
            TemplateStep(
                ref_id="validate_data",
                name="Validate Data",
                type="condition",
                config={
                    "branches": [
                        {
                            "name": "valid",
                            "condition": {"field": "result.valid", "op": "eq", "value": True},
                            "next_steps": ["store_data"],
                        },
                        {
                            "name": "invalid",
                            "condition": {"field": "result.valid", "op": "eq", "value": False},
                            "next_steps": [],
                        },
                    ],
                    "default_branch": "invalid",
                },
                depends_on=["transform_data"],
                description="Validates transformed data before storing.",
            ),
            TemplateStep(
                ref_id="store_data",
                name="Store Data",
                type="tool",
                config={"tool": "store", "destination": ""},
                depends_on=["validate_data"],
                description="Persists validated data to destination.",
            ),
        ],
        triggers=[
            TemplateTrigger(
                event_pattern="schedule.hourly",
                description="Fires on hourly schedule.",
            ),
        ],
    )

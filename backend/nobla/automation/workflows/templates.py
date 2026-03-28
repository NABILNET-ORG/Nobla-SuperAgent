"""Workflow template models — reusable workflow blueprints + import/export (Phase 6).

Core models:
    TemplateCategory   — Classification enum for template discovery
    TemplateStep       — Portable step definition (no runtime IDs)
    TemplateTrigger    — Portable trigger definition
    WorkflowTemplate   — Shareable workflow blueprint with metadata
    WorkflowExportData — Serialized workflow for import/export

Portable JSON format uses ``$nobla_version`` to track schema evolution.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# Current portable JSON schema version
SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TemplateCategory(str, Enum):
    """Classification for template discovery and filtering."""

    CI_CD = "ci_cd"
    NOTIFICATIONS = "notifications"
    DATA_PIPELINE = "data_pipeline"
    DEVOPS = "devops"
    APPROVAL = "approval"
    INTEGRATION = "integration"
    MONITORING = "monitoring"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Portable step / trigger (no runtime IDs)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TemplateStep:
    """Portable step definition for templates and export/import.

    Uses ``ref_id`` (short, human-readable) instead of UUID ``step_id``.
    ``depends_on`` references other ``ref_id`` values.

    Attributes:
        ref_id: Short reference ID (e.g. "check_status", "notify").
        name: Human-readable step name.
        type: Step type string (tool/agent/condition/webhook/delay/approval).
        config: Type-specific configuration dict.
        depends_on: List of ref_ids this step depends on.
        error_handling: Error handling strategy string.
        max_retries: Max retry attempts.
        timeout_seconds: Max execution time (None = no limit).
        description: What this step does (for template documentation).
    """

    ref_id: str = ""
    name: str = ""
    type: str = "tool"
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    error_handling: str = "fail"
    max_retries: int = 0
    timeout_seconds: int | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to portable dict."""
        d: dict[str, Any] = {
            "ref_id": self.ref_id,
            "name": self.name,
            "type": self.type,
            "config": self.config,
            "depends_on": self.depends_on,
            "error_handling": self.error_handling,
            "max_retries": self.max_retries,
        }
        if self.timeout_seconds is not None:
            d["timeout_seconds"] = self.timeout_seconds
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateStep:
        """Deserialize from portable dict."""
        return cls(
            ref_id=data.get("ref_id", ""),
            name=data.get("name", ""),
            type=data.get("type", "tool"),
            config=data.get("config", {}),
            depends_on=data.get("depends_on", []),
            error_handling=data.get("error_handling", "fail"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
            description=data.get("description", ""),
        )


@dataclass(slots=True)
class TemplateTrigger:
    """Portable trigger definition for templates and export/import.

    Attributes:
        event_pattern: fnmatch-compatible pattern (e.g. "webhook.github.*").
        conditions: List of condition dicts (field_path, operator, value).
        description: What this trigger responds to (for documentation).
    """

    event_pattern: str = "*"
    conditions: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to portable dict."""
        d: dict[str, Any] = {
            "event_pattern": self.event_pattern,
            "conditions": self.conditions,
        }
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateTrigger:
        """Deserialize from portable dict."""
        return cls(
            event_pattern=data.get("event_pattern", "*"),
            conditions=data.get("conditions", []),
            description=data.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Workflow template
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkflowTemplate:
    """Shareable workflow blueprint with metadata.

    Templates are versioned independently from workflow instances.
    They contain portable step/trigger definitions that get hydrated
    with real UUIDs when instantiated into a live workflow.

    Attributes:
        template_id: Unique identifier.
        name: Human-readable template name.
        description: What this template does.
        category: Classification for discovery.
        tags: Searchable tags (e.g. ["github", "ci", "notifications"]).
        author: Who created this template.
        version: Template version string (semver-style).
        steps: Portable step definitions.
        triggers: Portable trigger definitions.
        icon: Optional icon identifier for UI display.
        bundled: Whether this is a built-in template (not user-created).
        created_at: When this template was created.
        updated_at: When this template was last modified.
    """

    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    category: TemplateCategory = TemplateCategory.CUSTOM
    tags: list[str] = field(default_factory=list)
    author: str = ""
    version: str = "1.0.0"
    steps: list[TemplateStep] = field(default_factory=list)
    triggers: list[TemplateTrigger] = field(default_factory=list)
    icon: str = ""
    bundled: bool = False
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to portable dict (suitable for JSON export)."""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "tags": self.tags,
            "author": self.author,
            "version": self.version,
            "steps": [s.to_dict() for s in self.steps],
            "triggers": [t.to_dict() for t in self.triggers],
            "icon": self.icon,
            "bundled": self.bundled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowTemplate:
        """Deserialize from portable dict."""
        created = data.get("created_at", "")
        updated = data.get("updated_at", "")
        return cls(
            template_id=data.get("template_id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=TemplateCategory(data.get("category", "custom")),
            tags=data.get("tags", []),
            author=data.get("author", ""),
            version=data.get("version", "1.0.0"),
            steps=[TemplateStep.from_dict(s) for s in data.get("steps", [])],
            triggers=[TemplateTrigger.from_dict(t) for t in data.get("triggers", [])],
            icon=data.get("icon", ""),
            bundled=data.get("bundled", False),
            created_at=datetime.fromisoformat(created) if created else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(updated) if updated else datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Export / Import data envelope
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkflowExportData:
    """Portable envelope for workflow export/import.

    Wraps workflow content with schema metadata so imports can
    validate compatibility and migrate if needed.

    Attributes:
        nobla_version: Schema version for forward/backward compatibility.
        exported_at: When the export was generated.
        source_workflow_id: Original workflow ID (informational only).
        source_workflow_version: Version that was exported.
        name: Workflow name.
        description: Workflow description.
        steps: Portable step definitions.
        triggers: Portable trigger definitions.
        metadata: Arbitrary extra data (tags, author, etc.).
    """

    nobla_version: str = SCHEMA_VERSION
    exported_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source_workflow_id: str = ""
    source_workflow_version: int = 1
    name: str = ""
    description: str = ""
    steps: list[TemplateStep] = field(default_factory=list)
    triggers: list[TemplateTrigger] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to portable dict for JSON export."""
        return {
            "$nobla_version": self.nobla_version,
            "exported_at": self.exported_at.isoformat(),
            "source": {
                "workflow_id": self.source_workflow_id,
                "workflow_version": self.source_workflow_version,
            },
            "workflow": {
                "name": self.name,
                "description": self.description,
                "steps": [s.to_dict() for s in self.steps],
                "triggers": [t.to_dict() for t in self.triggers],
            },
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowExportData:
        """Deserialize from portable dict.

        Raises:
            ValueError: If ``$nobla_version`` is missing or unsupported.
        """
        version = data.get("$nobla_version", "")
        if not version:
            raise ValueError("Missing $nobla_version in export data")

        major = version.split(".")[0] if version else ""
        current_major = SCHEMA_VERSION.split(".")[0]
        if major != current_major:
            raise ValueError(
                f"Unsupported schema version {version!r}, "
                f"expected major version {current_major}"
            )

        exported = data.get("exported_at", "")
        source = data.get("source", {})
        workflow = data.get("workflow", {})

        return cls(
            nobla_version=version,
            exported_at=(
                datetime.fromisoformat(exported)
                if exported
                else datetime.now(timezone.utc)
            ),
            source_workflow_id=source.get("workflow_id", ""),
            source_workflow_version=source.get("workflow_version", 1),
            name=workflow.get("name", ""),
            description=workflow.get("description", ""),
            steps=[
                TemplateStep.from_dict(s)
                for s in workflow.get("steps", [])
            ],
            triggers=[
                TemplateTrigger.from_dict(t)
                for t in workflow.get("triggers", [])
            ],
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> WorkflowExportData:
        """Parse JSON string into WorkflowExportData.

        Raises:
            ValueError: If JSON is invalid or schema version is wrong.
            json.JSONDecodeError: If JSON parsing fails.
        """
        data = json.loads(json_str)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Conversion helpers — Workflow <-> portable format
# ---------------------------------------------------------------------------


def workflow_step_to_template_step(
    step: Any,
    ref_id_map: dict[str, str] | None = None,
) -> TemplateStep:
    """Convert a WorkflowStep to a portable TemplateStep.

    Args:
        step: A WorkflowStep instance.
        ref_id_map: Mapping from step_id (UUID) to short ref_id.
            If None, a sanitized version of the step name is used.

    Returns:
        Portable TemplateStep with ref_id instead of UUID.
    """
    if ref_id_map and step.step_id in ref_id_map:
        ref_id = ref_id_map[step.step_id]
    else:
        # Generate ref_id from name: lowercase, replace spaces with underscores
        ref_id = step.name.lower().replace(" ", "_").replace("-", "_")
        # Remove non-alphanumeric/underscore chars
        ref_id = "".join(c for c in ref_id if c.isalnum() or c == "_")
        ref_id = ref_id or f"step_{step.step_id[:8]}"

    # Remap depends_on UUIDs to ref_ids
    depends_on = []
    if ref_id_map:
        for dep_id in step.depends_on:
            depends_on.append(ref_id_map.get(dep_id, dep_id))
    else:
        depends_on = list(step.depends_on)

    return TemplateStep(
        ref_id=ref_id,
        name=step.name,
        type=step.type.value if hasattr(step.type, "value") else str(step.type),
        config=copy.deepcopy(step.config),
        depends_on=depends_on,
        error_handling=(
            step.error_handling.value
            if hasattr(step.error_handling, "value")
            else str(step.error_handling)
        ),
        max_retries=step.max_retries,
        timeout_seconds=step.timeout_seconds,
    )


def workflow_trigger_to_template_trigger(trigger: Any) -> TemplateTrigger:
    """Convert a WorkflowTrigger to a portable TemplateTrigger.

    Args:
        trigger: A WorkflowTrigger instance.

    Returns:
        Portable TemplateTrigger without runtime IDs.
    """
    conditions = []
    for cond in trigger.conditions:
        conditions.append({
            "field_path": cond.field_path,
            "operator": (
                cond.operator.value
                if hasattr(cond.operator, "value")
                else str(cond.operator)
            ),
            "value": cond.value,
        })

    return TemplateTrigger(
        event_pattern=trigger.event_pattern,
        conditions=conditions,
    )

"""Native Nobla skill format adapter.

Detects skill.json with nobla_version field. Loads directly without
translation since this is the native format.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nobla.security.permissions import Tier
from nobla.skills.adapter import FormatAdapter
from nobla.skills.models import (
    NoblaSkill,
    SkillCategory,
    SkillManifest,
    SkillSource,
)

logger = logging.getLogger(__name__)


class NoblaFormatSkill(NoblaSkill):
    """Skill loaded from native Nobla format.

    In Phase 5-Foundation, this is a simple passthrough. Full sandbox
    execution is wired in Phase 5A via SkillRuntime.
    """

    def __init__(self, manifest: SkillManifest, entry_point: dict[str, Any]) -> None:
        self.manifest = manifest
        self._entry_point = entry_point

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the skill. Placeholder for sandbox delegation."""
        return {
            "status": "executed",
            "skill": self.manifest.name,
            "params": params,
        }

    async def validate(self, params: dict[str, Any]) -> None:
        """Validate params against manifest config_schema if present."""
        # Full JSON Schema validation will be added when skills go live
        pass


class NoblaAdapter(FormatAdapter):
    """Adapter for native Nobla skill format (skill.json with nobla_version)."""

    source = SkillSource.NOBLA

    def can_handle(self, source: str | dict | Path) -> bool:
        """Detect native Nobla format: dict/file with 'nobla_version' key."""
        data = _load_manifest_data(source)
        if data is None:
            return False
        return "nobla_version" in data

    async def import_skill(self, source: str | dict | Path) -> NoblaSkill:
        """Import a native Nobla skill."""
        data = _load_manifest_data(source)
        if data is None:
            raise ValueError(f"Cannot load skill manifest from: {source}")

        manifest = SkillManifest(
            id=data.get("id", f"nobla://{data.get('name', 'unknown')}"),
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            source=SkillSource.NOBLA,
            author=data.get("author", "unknown"),
            category=_parse_category(data.get("category", "utilities")),
            tier=_parse_tier(data.get("tier", "STANDARD")),
            requires_approval=data.get("requires_approval", True),
            enabled=False,  # Always false — no exceptions
            capabilities=data.get("capabilities", []),
            dependencies=data.get("dependencies", []),
            config_schema=data.get("config_schema"),
            original_format=data,
        )

        return NoblaFormatSkill(
            manifest=manifest,
            entry_point=data.get("entry_point", {}),
        )


def _load_manifest_data(source: str | dict | Path) -> dict[str, Any] | None:
    """Load manifest data from a dict, file path, or JSON string."""
    if isinstance(source, dict):
        return source

    if isinstance(source, Path):
        if source.exists() and source.suffix == ".json":
            return json.loads(source.read_text(encoding="utf-8"))
        return None

    if isinstance(source, str):
        # Try as file path first
        p = Path(source)
        if p.exists() and p.suffix == ".json":
            return json.loads(p.read_text(encoding="utf-8"))
        # Try as JSON string
        try:
            return json.loads(source)
        except (json.JSONDecodeError, ValueError):
            return None

    return None


def _parse_category(value: str) -> SkillCategory:
    """Parse a category string into SkillCategory, defaulting to UTILITIES."""
    try:
        return SkillCategory(value.lower())
    except ValueError:
        return SkillCategory.UTILITIES


def _parse_tier(value: str) -> Tier:
    """Parse a tier string into Tier, defaulting to STANDARD."""
    try:
        return Tier[value.upper()]
    except (KeyError, ValueError):
        return Tier.STANDARD

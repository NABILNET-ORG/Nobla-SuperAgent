"""Universal skill adapter — detects format and imports skills from any source.

Spec reference: Phase 5-Foundation §4.3 — Universal Adapter.

Detection priority:
1. MCP — URL with /mcp, stdio://, or MCP manifest JSON
2. OpenClaw — skill.json with openclaw_version or claw_ prefixed keys
3. Claude — .md with YAML frontmatter containing name: + description:
4. LangChain — Python module with Tool or BaseTool subclass
5. Nobla — skill.json with nobla_version field (native)
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from nobla.skills.models import NoblaSkill, SkillSource

logger = logging.getLogger(__name__)


class FormatAdapter(ABC):
    """Base class for format-specific skill adapters."""

    source: SkillSource

    @abstractmethod
    def can_handle(self, source: str | dict | Path) -> bool:
        """Return True if this adapter can handle the given source."""
        ...

    @abstractmethod
    async def import_skill(self, source: str | dict | Path) -> NoblaSkill:
        """Import and normalize a skill from the given source."""
        ...


class UniversalSkillAdapter:
    """Detects skill format and delegates to the appropriate adapter.

    Adapters are tried in priority order. The first one whose can_handle()
    returns True wins.
    """

    def __init__(self, adapters: list[FormatAdapter] | None = None) -> None:
        self._adapters: list[FormatAdapter] = adapters or []

    def register_adapter(self, adapter: FormatAdapter) -> None:
        """Add a format adapter. Later adapters have lower priority."""
        self._adapters.append(adapter)

    def detect_format(self, source: str | dict | Path) -> SkillSource | None:
        """Detect the format of a skill source without importing it."""
        for adapter in self._adapters:
            if adapter.can_handle(source):
                return adapter.source
        return None

    async def import_skill(self, source: str | dict | Path) -> NoblaSkill:
        """Detect format and import a skill.

        Raises ValueError if no adapter can handle the source.
        """
        for adapter in self._adapters:
            if adapter.can_handle(source):
                logger.info(
                    "Importing skill via %s adapter from %s",
                    adapter.source.value,
                    _source_label(source),
                )
                return await adapter.import_skill(source)

        raise ValueError(
            f"No adapter can handle skill source: {_source_label(source)}"
        )


def _source_label(source: str | dict | Path) -> str:
    """Short label for logging."""
    if isinstance(source, Path):
        return str(source)
    if isinstance(source, dict):
        return f"dict({source.get('name', 'unknown')})"
    if len(source) > 80:
        return source[:77] + "..."
    return source

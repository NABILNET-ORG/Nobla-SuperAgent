"""ElementTargetingTool — natural language description to screen coordinates."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from difflib import SequenceMatcher

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry, register_tool
from nobla.tools.vision.cache import element_cache, hash_thumbnail
from nobla.tools.vision.detection import DetectedElement

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


_registry = ToolRegistry()

_STOPWORDS = frozenset({
    "the", "a", "an", "this", "that", "my", "your", "its",
    "in", "on", "at", "to", "for", "of", "with", "by",
    "big", "small", "large", "click", "find", "locate",
})


@dataclass
class TargetResult:
    x: int
    y: int
    element: DetectedElement
    match_score: float


@dataclass
class _Match:
    element: DetectedElement
    score: float


@register_tool
class ElementTargetingTool(BaseTool):
    name = "ui.target_element"
    description = "Find a UI element by natural language description"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    @property
    def _capture(self):
        return _registry.get("screenshot.capture")

    @property
    def _detector(self):
        return _registry.get("ui.detect_elements")

    async def validate(self, params: ToolParams) -> None:
        if not get_settings().vision.enabled:
            raise ValueError("Vision tools disabled in settings")
        if "description" not in params.args:
            raise ValueError("Missing required parameter: description")

    def describe_action(self, params: ToolParams) -> str:
        desc = params.args.get("description", "")
        return f"Find element matching '{desc}'"

    async def target(
        self,
        description: str,
        monitor: int = 0,
        region: dict | None = None,
    ) -> TargetResult:
        """Internal API — composes capture + detect + match."""
        # 1. Capture screenshot
        capture_result = await self._capture.capture(monitor, region)

        # 2. Check element cache
        img_hash = hash_thumbnail(capture_result.image)
        cached = element_cache.get(img_hash)

        # 3. Detect elements if not cached
        if cached:
            elements = [DetectedElement(**e) for e in cached]
        else:
            elements = await self._detector.detect(capture_result.image)

        # 4. Fuzzy match
        match = self._best_match(description, elements)
        if not match:
            raise ValueError(f"No element matching '{description}' found")

        # 5. Return center coordinates
        bbox = match.element.bbox
        return TargetResult(
            x=bbox["x"] + bbox["width"] // 2,
            y=bbox["y"] + bbox["height"] // 2,
            element=match.element,
            match_score=match.score,
        )

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        description = args.get("description")

        if description is None:
            return ToolResult(success=False, error="Missing required parameter: description")

        monitor = args.get("monitor", 0)
        region = args.get("region")

        try:
            result = await self.target(description, monitor, region)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Targeting failed: {e}")

        return ToolResult(
            success=True,
            data={
                "x": result.x,
                "y": result.y,
                "element": asdict(result.element),
                "match_score": round(result.match_score, 4),
            },
        )

    def _extract_keywords(self, description: str) -> list[str]:
        words = description.lower().split()
        return [w for w in words if w not in _STOPWORDS]

    def _best_match(
        self, description: str, elements: list[DetectedElement]
    ) -> _Match | None:
        keywords = self._extract_keywords(description)
        if not keywords:
            return None

        scored: list[_Match] = []
        desc_lower = description.lower()

        for el in elements:
            label_lower = el.label.lower()

            # Keyword matching
            hits = sum(
                1
                for kw in keywords
                if kw in label_lower
                or SequenceMatcher(None, kw, label_lower).ratio() > 0.6
            )
            ratio_score = hits / len(keywords)

            # Best single keyword — prevents dilution
            best_kw = max(
                (SequenceMatcher(None, kw, label_lower).ratio() for kw in keywords),
                default=0.0,
            )
            text_score = max(ratio_score, best_kw)

            # Type bonus
            type_score = 1.0 if el.element_type in desc_lower else 0.0

            # Combined score weighted by detection confidence
            score = ((text_score * 0.7) + (type_score * 0.3)) * el.confidence

            if score > 0.3:
                scored.append(_Match(element=el, score=score))

        return max(scored, key=lambda m: m.score, default=None)

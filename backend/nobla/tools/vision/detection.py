"""UIDetectionTool — UI element detection with OCR heuristics + UI-TARS stub."""
from __future__ import annotations

import base64
from dataclasses import dataclass, asdict
from io import BytesIO

from PIL import Image

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry, register_tool
from nobla.tools.vision.cache import element_cache, hash_thumbnail

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


_registry = ToolRegistry()


@dataclass
class DetectedElement:
    element_type: str
    label: str
    bbox: dict
    confidence: float


@register_tool
class UIDetectionTool(BaseTool):
    name = "ui.detect_elements"
    description = "Detect UI elements in a screenshot"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    def _get_ocr_tool(self):
        return _registry.get("ocr.extract")

    async def validate(self, params: ToolParams) -> None:
        if not get_settings().vision.enabled:
            raise ValueError("Vision tools disabled in settings")
        if "image_b64" not in params.args:
            raise ValueError("Missing required parameter: image_b64")

    def describe_action(self, params: ToolParams) -> str:
        return "Detect UI elements in screenshot"

    async def detect(self, image: Image.Image) -> list[DetectedElement]:
        """Internal API — returns detected elements, writes to cache."""
        if get_settings().vision.ui_tars_enabled:
            try:
                elements = await self._uitars_detect(image)
                img_hash = hash_thumbnail(image)
                element_cache.put(img_hash, [asdict(e) for e in elements])
                return elements
            except Exception:
                pass  # Fall through to OCR-based

        elements = await self._ocr_based_detect(image)
        img_hash = hash_thumbnail(image)
        element_cache.put(img_hash, [asdict(e) for e in elements])
        return elements

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        try:
            raw = base64.b64decode(args["image_b64"])
            image = Image.open(BytesIO(raw))
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid image: {e}")

        try:
            elements = await self.detect(image)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        # Apply element_types filter if requested
        type_filter = args.get("element_types")
        if type_filter:
            elements = [e for e in elements if e.element_type in type_filter]

        return ToolResult(
            success=True,
            data={
                "elements": [asdict(e) for e in elements],
                "count": len(elements),
                "method": "ui_tars" if get_settings().vision.ui_tars_enabled else "ocr_heuristic",
            },
        )

    async def _uitars_detect(self, image: Image.Image) -> list[DetectedElement]:
        if not get_settings().vision.ui_tars_model_path:
            raise RuntimeError("UI-TARS model path not configured")
        raise NotImplementedError("UI-TARS inference not yet implemented")

    async def _ocr_based_detect(self, image: Image.Image) -> list[DetectedElement]:
        ocr_tool = self._get_ocr_tool()
        if ocr_tool is None:
            raise RuntimeError("OCR tool not available")

        ocr_result = await ocr_tool.extract(image)
        threshold = get_settings().vision.detection_confidence_threshold

        elements: list[DetectedElement] = []
        for block in ocr_result.blocks:
            element_type = self._classify_element(image, block)
            confidence = block.confidence * 0.7  # discount vs UI-TARS
            if confidence >= threshold:
                elements.append(
                    DetectedElement(
                        element_type=element_type,
                        label=block.text,
                        bbox=block.bbox,
                        confidence=round(confidence, 4),
                    )
                )
        return elements

    def _classify_element(self, image: Image.Image, block) -> str:
        text = block.text.strip()
        bbox = block.bbox

        # URL pattern -> link
        if text.startswith(("http://", "https://", "www.")):
            return "link"

        # Label pattern (ends with ":")
        if text.endswith(":"):
            return "label"

        # Short text with distinct background -> button
        has_bg = self._has_distinct_background(image, bbox)
        word_count = len(text.split())
        if word_count <= 3 and has_bg:
            return "button"

        # Tall text -> heading
        if bbox.get("height", 0) > 30:
            return "heading"

        return "text"

    def _has_distinct_background(self, image: Image.Image, bbox: dict) -> bool:
        x, y = bbox.get("x", 0), bbox.get("y", 0)
        w, h = bbox.get("width", 0), bbox.get("height", 0)
        pad = 4

        try:
            inside = image.getpixel((x + w // 2, y + h // 2))
            outside_samples = [
                image.getpixel((max(0, x - pad), y + h // 2)),
                image.getpixel((min(image.width - 1, x + w + pad), y + h // 2)),
                image.getpixel((x + w // 2, max(0, y - pad))),
                image.getpixel((x + w // 2, min(image.height - 1, y + h + pad))),
            ]
        except (IndexError, Exception):
            return False

        for outside in outside_samples:
            diff = sum(abs(a - b) for a, b in zip(inside[:3], outside[:3]))
            if diff > 80:
                return True
        return False

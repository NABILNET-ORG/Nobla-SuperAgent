"""OCRTool — extract text from images using Tesseract (primary) or EasyOCR (fallback)."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from io import BytesIO
from typing import List

from PIL import Image

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

# ---------------------------------------------------------------------------
# Lazy settings singleton
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ---------------------------------------------------------------------------
# Optional engine imports
# ---------------------------------------------------------------------------

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore[assignment]

try:
    import easyocr as easyocr_module
except ImportError:
    easyocr_module = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    """A single recognized text region."""

    text: str
    confidence: float
    bbox: dict  # {x, y, width, height}


@dataclass
class OCRResult:
    """Aggregated result from an OCR pass."""

    blocks: list[TextBlock]
    full_text: str
    engine_used: str


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@register_tool
class OCRTool(BaseTool):
    """Extract text from images using Tesseract (primary) or EasyOCR (fallback)."""

    name = "ocr.extract"
    description = "Extract text from an image using OCR (Tesseract or EasyOCR)"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    def __init__(self) -> None:
        super().__init__()
        self._easyocr_reader = None
        self._reader_langs: list[str] | None = None

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    async def validate(self, params: ToolParams) -> None:
        if not get_settings().vision.enabled:
            raise ValueError("Vision tools disabled in settings")
        if not params.args.get("image_b64"):
            raise ValueError("image_b64 is required")

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        engine = args.get("engine") or get_settings().vision.ocr_engine
        langs = args.get("languages") or get_settings().vision.ocr_languages
        return f"Extract text using {engine} (languages: {', '.join(langs)})"

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        try:
            image = self._decode_b64(args["image_b64"])
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to decode image: {exc}")

        languages: list[str] = args.get("languages") or get_settings().vision.ocr_languages
        engine: str | None = args.get("engine")

        try:
            result = await self.extract(image, languages=languages, engine=engine)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            data={
                "blocks": [
                    {
                        "text": b.text,
                        "confidence": b.confidence,
                        "bbox": b.bbox,
                    }
                    for b in result.blocks
                ],
                "full_text": result.full_text,
                "engine_used": result.engine_used,
            },
        )

    # ------------------------------------------------------------------
    # Public internal API (called by UIDetectionTool, ElementTargetingTool)
    # ------------------------------------------------------------------

    async def extract(
        self,
        image: Image.Image,
        languages: list[str] | None = None,
        engine: str | None = None,
    ) -> OCRResult:
        """Extract text from a PIL.Image.

        Tries the preferred engine first; falls back to the other engine on any
        error.  Raises RuntimeError if neither engine is available.
        """
        if languages is None:
            languages = get_settings().vision.ocr_languages

        preferred = engine or get_settings().vision.ocr_engine
        other = "easyocr" if preferred == "tesseract" else "tesseract"
        engines = {
            "tesseract": self._tesseract_extract,
            "easyocr": self._easyocr_extract,
        }

        try:
            return await engines[preferred](image, languages)
        except (ImportError, TypeError, Exception):
            pass

        try:
            return await engines[other](image, languages)
        except (ImportError, TypeError, Exception):
            pass

        raise RuntimeError(
            "No OCR engine available. "
            "Install pytesseract (pip install pytesseract) or "
            "easyocr (pip install easyocr)."
        )

    # ------------------------------------------------------------------
    # Engine implementations
    # ------------------------------------------------------------------

    async def _tesseract_extract(
        self, image: Image.Image, languages: list[str]
    ) -> OCRResult:
        """Run Tesseract OCR in a thread pool."""
        if pytesseract is None:
            raise ImportError(
                "pytesseract not installed. Run: pip install pytesseract"
            )

        lang_str = "+".join(languages)
        threshold = get_settings().vision.ocr_confidence_threshold

        data = await asyncio.to_thread(
            pytesseract.image_to_data,
            image,
            lang=lang_str,
            output_type=pytesseract.Output.DICT,
        )

        blocks: list[TextBlock] = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if not text:
                continue
            raw_conf = data["conf"][i]
            try:
                raw_conf = int(raw_conf)
            except (ValueError, TypeError):
                continue
            if raw_conf < 0:
                continue
            confidence = raw_conf / 100.0
            if confidence < threshold:
                continue
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=confidence,
                    bbox={
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "width": data["width"][i],
                        "height": data["height"][i],
                    },
                )
            )

        full_text = " ".join(b.text for b in blocks)
        return OCRResult(blocks=blocks, full_text=full_text, engine_used="tesseract")

    async def _easyocr_extract(
        self, image: Image.Image, languages: list[str]
    ) -> OCRResult:
        """Run EasyOCR in a thread pool."""
        if easyocr_module is None:
            raise ImportError(
                "easyocr not installed. Run: pip install easyocr"
            )

        import numpy as np  # lazy — only needed when easyocr is available

        threshold = get_settings().vision.ocr_confidence_threshold
        reader = await self._get_reader(languages)

        img_array = np.array(image)
        raw_results = await asyncio.to_thread(reader.readtext, img_array)

        blocks: list[TextBlock] = []
        for bbox_points, text, confidence in raw_results:
            text = text.strip()
            if not text:
                continue
            if confidence < threshold:
                continue
            # bbox_points: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            x1 = bbox_points[0][0]
            y1 = bbox_points[0][1]
            x2 = bbox_points[2][0]
            y2 = bbox_points[2][1]
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=confidence,
                    bbox={
                        "x": x1,
                        "y": y1,
                        "width": x2 - x1,
                        "height": y2 - y1,
                    },
                )
            )

        full_text = " ".join(b.text for b in blocks)
        return OCRResult(blocks=blocks, full_text=full_text, engine_used="easyocr")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_reader(self, languages: list[str]):
        """Lazy singleton EasyOCR reader; recreated if languages change."""
        if self._easyocr_reader is None or self._reader_langs != languages:
            self._easyocr_reader = await asyncio.to_thread(
                easyocr_module.Reader, languages, gpu=False
            )
            self._reader_langs = languages
        return self._easyocr_reader

    @staticmethod
    def _decode_b64(image_b64: str) -> Image.Image:
        """Decode a base64-encoded image string to a PIL.Image."""
        raw = base64.b64decode(image_b64)
        return Image.open(BytesIO(raw)).convert("RGB")

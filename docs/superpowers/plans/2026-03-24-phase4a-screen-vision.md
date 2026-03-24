# Phase 4A: Screen Vision — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 4 vision tools (screenshot capture, OCR, UI detection, NL element targeting) that plug into the existing tool platform, enabling Nobla Agent to see and interpret the screen.

**Architecture:** Each tool inherits `BaseTool`, registers via `@register_tool`, and exposes a dual interface — public `execute()` for the tool platform (JSON-safe) and internal methods for direct composition between vision tools. Inline fallback (Tesseract→EasyOCR, UI-TARS stub→OCR heuristics). Shared `ElementCache` in `cache.py` with TTL. All blocking calls wrapped in `asyncio.to_thread()`.

**Tech Stack:** python-mss, Pillow, pytesseract, easyocr (optional), asyncio, difflib (stdlib)

**Spec:** `docs/superpowers/specs/2026-03-24-phase4a-screen-vision-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/nobla/config/settings.py` | Add `VisionSettings` to `Settings` |
| Modify | `backend/pyproject.toml` | Add `vision` and `vision-full` optional dependency groups |
| Create | `backend/nobla/tools/vision/__init__.py` | Auto-discovery imports for `@register_tool` |
| Create | `backend/nobla/tools/vision/cache.py` | `ElementCache` + `hash_thumbnail` + `element_cache` singleton |
| Create | `backend/nobla/tools/vision/capture.py` | `ScreenshotTool` — mss-based screen capture |
| Create | `backend/nobla/tools/vision/ocr.py` | `OCRTool` — Tesseract + EasyOCR fallback |
| Create | `backend/nobla/tools/vision/detection.py` | `UIDetectionTool` — OCR-based heuristics + UI-TARS stub |
| Create | `backend/nobla/tools/vision/targeting.py` | `ElementTargetingTool` — NL description → (x,y) coordinates |
| Modify | `backend/nobla/tools/__init__.py` | Add `from nobla.tools import vision` for auto-discovery |
| Create | `backend/tests/test_vision_settings.py` | Unit tests for VisionSettings |
| Create | `backend/tests/test_vision_cache.py` | Unit tests for ElementCache + hash_thumbnail |
| Create | `backend/tests/test_vision_capture.py` | Unit tests for ScreenshotTool (mocked mss) |
| Create | `backend/tests/test_vision_ocr.py` | Unit tests for OCRTool (mocked engines) |
| Create | `backend/tests/test_vision_detection.py` | Unit tests for UIDetectionTool (mocked OCR) |
| Create | `backend/tests/test_vision_targeting.py` | Unit tests for ElementTargetingTool (mocked capture + detection) |
| Create | `backend/tests/integration/test_vision_flow.py` | E2E WebSocket integration tests |

---

## Task 0: VisionSettings & Dependencies

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/test_vision_settings.py`

- [ ] **Step 1: Write the failing test for VisionSettings**

```python
# backend/tests/test_vision_settings.py
"""Unit tests for VisionSettings."""
from __future__ import annotations

import pytest
from nobla.config.settings import Settings, VisionSettings


class TestVisionSettings:
    def test_defaults(self):
        s = VisionSettings()
        assert s.enabled is True
        assert s.screenshot_format == "png"
        assert s.screenshot_quality == 85
        assert s.screenshot_max_dimension == 1920
        assert s.screenshot_include_cursor is False
        assert s.ocr_engine == "tesseract"
        assert s.ocr_languages == ["en"]
        assert s.ocr_confidence_threshold == 0.5
        assert s.ui_tars_enabled is False
        assert s.ui_tars_model_path == ""
        assert s.detection_confidence_threshold == 0.4
        assert s.element_cache_ttl == 5

    def test_custom_values(self):
        s = VisionSettings(
            screenshot_format="jpeg",
            ocr_languages=["en", "ara"],
            ui_tars_enabled=True,
            ui_tars_model_path="/models/uitars.bin",
        )
        assert s.screenshot_format == "jpeg"
        assert s.ocr_languages == ["en", "ara"]
        assert s.ui_tars_enabled is True

    def test_wired_into_settings(self):
        s = Settings()
        assert hasattr(s, "vision")
        assert isinstance(s.vision, VisionSettings)
        assert s.vision.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_vision_settings.py -v`
Expected: FAIL — `VisionSettings` does not exist yet.

- [ ] **Step 3: Add VisionSettings to config/settings.py**

Add after `ToolPlatformSettings` class:

```python
class VisionSettings(BaseModel):
    """Screen vision tools configuration."""

    enabled: bool = True
    screenshot_format: str = "png"
    screenshot_quality: int = 85
    screenshot_max_dimension: int = 1920
    screenshot_include_cursor: bool = False
    ocr_engine: str = "tesseract"
    ocr_languages: list[str] = ["en"]
    ocr_confidence_threshold: float = 0.5
    ui_tars_enabled: bool = False
    ui_tars_model_path: str = ""
    detection_confidence_threshold: float = 0.4
    element_cache_ttl: int = 5
```

Add to `Settings` class (after `tools` field):

```python
    vision: VisionSettings = Field(default_factory=VisionSettings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_vision_settings.py -v`
Expected: 3 passed.

- [ ] **Step 5: Add optional dependencies to pyproject.toml**

Find the `[project.optional-dependencies]` section (or create it) and add:

```toml
vision = ["python-mss>=9.0", "Pillow>=10.0", "pytesseract>=0.3"]
vision-full = ["python-mss>=9.0", "Pillow>=10.0", "pytesseract>=0.3", "easyocr>=1.7"]
```

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/config/settings.py backend/pyproject.toml backend/tests/test_vision_settings.py
git commit -m "feat(config): add VisionSettings + vision dependency groups"
```

---

## Task 1: ElementCache

**Files:**
- Create: `backend/nobla/tools/vision/__init__.py` (empty placeholder for now)
- Create: `backend/nobla/tools/vision/cache.py`
- Create: `backend/tests/test_vision_cache.py`

- [ ] **Step 1: Create vision package placeholder**

```python
# backend/nobla/tools/vision/__init__.py
"""Vision tools — screen capture, OCR, element detection, targeting."""
```

- [ ] **Step 2: Write failing tests for ElementCache**

```python
# backend/tests/test_vision_cache.py
"""Unit tests for ElementCache and hash_thumbnail."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from nobla.tools.vision.cache import ElementCache, hash_thumbnail


class TestElementCache:
    def test_put_and_get(self):
        cache = ElementCache(ttl=5)
        elements = [{"element_type": "button", "label": "OK", "bbox": {}, "confidence": 0.9}]
        cache.put("hash123", elements)
        assert cache.get("hash123") == elements

    def test_miss_on_different_hash(self):
        cache = ElementCache(ttl=5)
        cache.put("hash123", [{"label": "OK"}])
        assert cache.get("hash456") is None

    def test_miss_on_expired_ttl(self):
        cache = ElementCache(ttl=1)
        with patch("nobla.tools.vision.cache.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            cache.put("hash123", [{"label": "OK"}])
            mock_time.monotonic.return_value = 102.0  # 2s later, TTL=1 expired
            assert cache.get("hash123") is None

    def test_miss_on_empty_cache(self):
        cache = ElementCache(ttl=5)
        assert cache.get("hash123") is None

    def test_clear(self):
        cache = ElementCache(ttl=5)
        cache.put("hash123", [{"label": "OK"}])
        cache.clear()
        assert cache.get("hash123") is None

    def test_put_overwrites_previous(self):
        cache = ElementCache(ttl=5)
        cache.put("hash1", [{"label": "A"}])
        cache.put("hash2", [{"label": "B"}])
        assert cache.get("hash1") is None
        assert cache.get("hash2") == [{"label": "B"}]


class TestHashThumbnail:
    def test_same_image_same_hash(self):
        from PIL import Image
        img = Image.new("RGB", (200, 200), color="red")
        assert hash_thumbnail(img) == hash_thumbnail(img)

    def test_different_image_different_hash(self):
        from PIL import Image
        img1 = Image.new("RGB", (200, 200), color="red")
        img2 = Image.new("RGB", (200, 200), color="blue")
        assert hash_thumbnail(img1) != hash_thumbnail(img2)

    def test_returns_string(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        result = hash_thumbnail(img)
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex digest length
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_vision_cache.py -v`
Expected: FAIL — `cache.py` does not exist.

- [ ] **Step 4: Implement cache.py**

```python
# backend/nobla/tools/vision/cache.py
"""Shared TTL cache for detected UI elements."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from PIL import Image


@dataclass
class CachedElements:
    elements: list[dict]
    screenshot_hash: str
    timestamp: float


class ElementCache:
    """Single-entry TTL cache for detected elements.

    Keyed by screenshot thumbnail hash. The most recent detection
    result is cached; older entries are evicted on put().
    """

    def __init__(self, ttl: int = 5):
        self._ttl = ttl
        self._entry: CachedElements | None = None

    def get(self, screenshot_hash: str) -> list[dict] | None:
        if (
            self._entry
            and self._entry.screenshot_hash == screenshot_hash
            and (time.monotonic() - self._entry.timestamp) < self._ttl
        ):
            return self._entry.elements
        return None

    def put(self, screenshot_hash: str, elements: list[dict]) -> None:
        self._entry = CachedElements(elements, screenshot_hash, time.monotonic())

    def clear(self) -> None:
        self._entry = None


def hash_thumbnail(image: Image.Image) -> str:
    """Fast image hash via 64x64 thumbnail. ~1ms vs ~50ms for full 4K."""
    thumb = image.resize((64, 64)).tobytes()
    return hashlib.md5(thumb).hexdigest()


# Module-level singleton. Imported by detection.py and targeting.py directly.
element_cache = ElementCache()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_vision_cache.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/vision/__init__.py backend/nobla/tools/vision/cache.py backend/tests/test_vision_cache.py
git commit -m "feat(vision): add ElementCache with TTL and thumbnail hashing"
```

---

## Task 2: ScreenshotTool

**Files:**
- Create: `backend/nobla/tools/vision/capture.py`
- Create: `backend/tests/test_vision_capture.py`

- [ ] **Step 1: Write failing tests for ScreenshotTool**

```python
# backend/tests/test_vision_capture.py
"""Unit tests for ScreenshotTool."""
from __future__ import annotations

import base64
from dataclasses import asdict
from io import BytesIO
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pytest_asyncio
from PIL import Image

from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.vision.capture import ScreenshotTool, CaptureResult
from nobla.security.permissions import Tier


def _make_params(args: dict | None = None) -> ToolParams:
    state = MagicMock()
    state.tier = Tier.STANDARD
    state.connection_id = "test-conn"
    return ToolParams(args=args or {}, connection_state=state)


def _fake_mss_grab(monitor_rect):
    """Return a fake mss screenshot object with .rgb and .size."""
    img = Image.new("RGB", (1920, 1080), color="blue")
    raw = img.tobytes()
    result = MagicMock()
    result.rgb = raw
    result.size = (1920, 1080)
    result.width = 1920
    result.height = 1080
    return result


class TestScreenshotToolMetadata:
    def test_tool_metadata(self):
        tool = ScreenshotTool()
        assert tool.name == "screenshot.capture"
        assert tool.category == ToolCategory.VISION
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    def test_describe_action_default(self):
        tool = ScreenshotTool()
        params = _make_params()
        desc = tool.describe_action(params)
        assert "screenshot" in desc.lower() or "capture" in desc.lower()

    def test_describe_action_with_region(self):
        tool = ScreenshotTool()
        params = _make_params({"region": {"x": 10, "y": 20, "width": 100, "height": 50}})
        desc = tool.describe_action(params)
        assert "region" in desc.lower()


class TestScreenshotToolValidate:
    @pytest.mark.asyncio
    async def test_validate_invalid_format(self):
        tool = ScreenshotTool()
        params = _make_params({"format": "bmp"})
        with pytest.raises(ValueError, match="format"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_validate_negative_region(self):
        tool = ScreenshotTool()
        params = _make_params({"region": {"x": -1, "y": 0, "width": 100, "height": 100}})
        with pytest.raises(ValueError, match="region"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_validate_valid_params(self):
        tool = ScreenshotTool()
        params = _make_params({"monitor": 0, "format": "png"})
        await tool.validate(params)  # Should not raise

    @pytest.mark.asyncio
    async def test_validate_vision_disabled(self):
        tool = ScreenshotTool()
        params = _make_params()
        with patch("nobla.tools.vision.capture.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_get_settings.return_value = mock_settings
            mock_settings.vision.enabled = False
            with pytest.raises(ValueError, match="disabled"):
                await tool.validate(params)


class TestScreenshotToolCapture:
    @pytest.mark.asyncio
    async def test_capture_returns_capture_result(self):
        tool = ScreenshotTool()
        with patch("nobla.tools.vision.capture.mss_module") as mock_mss:
            mock_ctx = MagicMock()
            mock_ctx.monitors = [
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
            mock_ctx.grab = MagicMock(side_effect=_fake_mss_grab)
            mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)

            result = await tool.capture()
            assert isinstance(result, CaptureResult)
            assert isinstance(result.image, Image.Image)
            assert result.width == 1920
            assert result.height == 1080

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result_with_base64(self):
        tool = ScreenshotTool()
        with patch("nobla.tools.vision.capture.mss_module") as mock_mss, \
             patch("nobla.tools.vision.capture.settings") as mock_settings:
            mock_settings.vision.enabled = True
            mock_settings.vision.screenshot_format = "png"
            mock_settings.vision.screenshot_quality = 85
            mock_settings.vision.screenshot_max_dimension = 1920

            mock_ctx = MagicMock()
            mock_ctx.monitors = [
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
            mock_ctx.grab = MagicMock(side_effect=_fake_mss_grab)
            mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)

            params = _make_params({"monitor": 0})
            result = await tool.execute(params)
            assert result.success is True
            assert "image_b64" in result.data
            # Verify it's valid base64 that decodes to an image
            img_bytes = base64.b64decode(result.data["image_b64"])
            img = Image.open(BytesIO(img_bytes))
            assert img.size[0] <= 1920

    @pytest.mark.asyncio
    async def test_execute_downscales_large_image(self):
        """4K image should be downscaled in returned base64."""
        tool = ScreenshotTool()

        def _fake_4k_grab(rect):
            img = Image.new("RGB", (3840, 2160), color="green")
            result = MagicMock()
            result.rgb = img.tobytes()
            result.size = (3840, 2160)
            result.width = 3840
            result.height = 2160
            return result

        with patch("nobla.tools.vision.capture.mss_module") as mock_mss, \
             patch("nobla.tools.vision.capture.settings") as mock_settings:
            mock_settings.vision.enabled = True
            mock_settings.vision.screenshot_format = "png"
            mock_settings.vision.screenshot_quality = 85
            mock_settings.vision.screenshot_max_dimension = 1920

            mock_ctx = MagicMock()
            mock_ctx.monitors = [
                {"left": 0, "top": 0, "width": 3840, "height": 2160},
                {"left": 0, "top": 0, "width": 3840, "height": 2160},
            ]
            mock_ctx.grab = MagicMock(side_effect=_fake_4k_grab)
            mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)

            params = _make_params()
            result = await tool.execute(params)
            assert result.data["native_width"] == 3840
            assert result.data["width"] <= 1920
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_vision_capture.py -v`
Expected: FAIL — `capture.py` does not exist.

- [ ] **Step 3: Implement capture.py**

```python
# backend/nobla/tools/vision/capture.py
"""ScreenshotTool — cross-platform screen capture using mss."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

try:
    import mss as mss_module
except ImportError:
    mss_module = None  # type: ignore[assignment]


@dataclass
class CaptureResult:
    """Internal capture result with raw PIL.Image."""

    image: Image.Image
    width: int
    height: int
    monitor: int


@register_tool
class ScreenshotTool(BaseTool):
    name = "screenshot.capture"
    description = "Capture a screenshot of the current screen"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        if not get_settings().vision.enabled:
            raise ValueError("Vision tools disabled in settings")
        if mss_module is None:
            raise ValueError(
                "python-mss not installed. Run: pip install nobla[vision]"
            )
        args = params.args
        fmt = args.get("format", get_settings().vision.screenshot_format)
        if fmt not in ("png", "jpeg", "jpg"):
            raise ValueError(f"Invalid format '{fmt}'. Must be 'png' or 'jpeg'.")
        region = args.get("region")
        if region:
            for key in ("x", "y", "width", "height"):
                val = region.get(key)
                if val is None or not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(
                        f"Invalid region: '{key}' must be a non-negative number."
                    )

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        monitor = args.get("monitor", 0)
        region = args.get("region")
        if region:
            return (
                f"Capture region ({region['x']}, {region['y']}, "
                f"{region['width']}, {region['height']}) on monitor {monitor}"
            )
        return f"Capture screenshot of monitor {monitor}"

    async def capture(
        self, monitor: int = 0, region: dict | None = None
    ) -> CaptureResult:
        """Internal API — returns raw PIL.Image at native resolution."""
        if mss_module is None:
            raise RuntimeError(
                "python-mss not installed. Run: pip install nobla[vision]"
            )

        def _grab():
            with mss_module.mss() as sct:
                if region:
                    rect = {
                        "left": int(region["x"]),
                        "top": int(region["y"]),
                        "width": int(region["width"]),
                        "height": int(region["height"]),
                    }
                else:
                    if monitor < 0 or monitor >= len(sct.monitors):
                        raise ValueError(
                            f"Monitor {monitor} not found. "
                            f"Available: 0-{len(sct.monitors) - 1}"
                        )
                    rect = sct.monitors[monitor]
                raw = sct.grab(rect)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
                return img

        image = await asyncio.to_thread(_grab)
        return CaptureResult(
            image=image,
            width=image.width,
            height=image.height,
            monitor=monitor,
        )

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        monitor = args.get("monitor", 0)
        region = args.get("region")

        try:
            result = await self.capture(monitor, region)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        fmt = args.get("format", get_settings().vision.screenshot_format)
        quality = args.get("quality", get_settings().vision.screenshot_quality)
        max_dim = get_settings().vision.screenshot_max_dimension

        # Downscale for return only — internal callers use capture() directly
        return_image = result.image
        native_w, native_h = return_image.width, return_image.height
        if max(native_w, native_h) > max_dim:
            scale = max_dim / max(native_w, native_h)
            new_w = int(native_w * scale)
            new_h = int(native_h * scale)
            return_image = return_image.resize(
                (new_w, new_h), Image.Resampling.LANCZOS
            )

        # Encode to base64
        buf = BytesIO()
        save_fmt = "JPEG" if fmt in ("jpeg", "jpg") else "PNG"
        save_kwargs = {"quality": quality} if save_fmt == "JPEG" else {}
        return_image.save(buf, format=save_fmt, **save_kwargs)
        image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return ToolResult(
            success=True,
            data={
                "image_b64": image_b64,
                "width": return_image.width,
                "height": return_image.height,
                "format": fmt,
                "monitor": monitor,
                "native_width": native_w,
                "native_height": native_h,
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_vision_capture.py -v`
Expected: All passed.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/vision/capture.py backend/tests/test_vision_capture.py
git commit -m "feat(vision): add ScreenshotTool with mss capture + downscaling"
```

---

## Task 3: OCRTool

**Files:**
- Create: `backend/nobla/tools/vision/ocr.py`
- Create: `backend/tests/test_vision_ocr.py`

- [ ] **Step 1: Write failing tests for OCRTool**

```python
# backend/tests/test_vision_ocr.py
"""Unit tests for OCRTool."""
from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from PIL import Image

from nobla.tools.models import ToolCategory, ToolParams
from nobla.tools.vision.ocr import OCRTool, TextBlock, OCRResult
from nobla.security.permissions import Tier


def _make_params(args: dict) -> ToolParams:
    state = MagicMock()
    state.tier = Tier.STANDARD
    state.connection_id = "test-conn"
    return ToolParams(args=args, connection_state=state)


def _fake_image_b64():
    """Create a small test image and return its base64."""
    import base64
    from io import BytesIO
    img = Image.new("RGB", (100, 50), color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestOCRToolMetadata:
    def test_tool_metadata(self):
        tool = OCRTool()
        assert tool.name == "ocr.extract"
        assert tool.category == ToolCategory.VISION
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False


class TestOCRToolValidate:
    @pytest.mark.asyncio
    async def test_validate_missing_image(self):
        tool = OCRTool()
        params = _make_params({})
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_s = MagicMock()
            mock_gs.return_value = mock_s
            mock_s.vision.enabled = True
            with pytest.raises(ValueError, match="image_b64"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_validate_vision_disabled(self):
        tool = OCRTool()
        params = _make_params({"image_b64": "abc"})
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_s = MagicMock()
            mock_gs.return_value = mock_s
            mock_s.vision.enabled = False
            with pytest.raises(ValueError, match="disabled"):
                await tool.validate(params)


class TestOCRToolExtract:
    @pytest.mark.asyncio
    async def test_tesseract_extract(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50), color="white")

        fake_data = {
            "text": ["Hello", "World", ""],
            "conf": [95.0, 87.0, -1.0],
            "left": [10, 60, 0],
            "top": [5, 5, 0],
            "width": [40, 40, 0],
            "height": [20, 20, 0],
        }

        with patch("nobla.tools.vision.ocr.pytesseract") as mock_tess, \
             patch("nobla.tools.vision.ocr.settings") as mock_s:
            mock_s.vision.ocr_engine = "tesseract"
            mock_s.vision.ocr_languages = ["en"]
            mock_s.vision.ocr_confidence_threshold = 0.5
            mock_tess.image_to_data.return_value = fake_data
            mock_tess.Output.DICT = "dict"

            result = await tool.extract(img)
            assert isinstance(result, OCRResult)
            assert result.engine_used == "tesseract"
            assert len(result.blocks) == 2  # empty text filtered
            assert result.blocks[0].text == "Hello"
            assert result.blocks[0].confidence == 0.95
            assert result.full_text == "Hello World"

    @pytest.mark.asyncio
    async def test_easyocr_extract(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50), color="white")

        fake_results = [
            ([[10, 5], [50, 5], [50, 25], [10, 25]], "Submit", 0.92),
            ([[60, 5], [100, 5], [100, 25], [60, 25]], "Cancel", 0.88),
        ]

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_s = MagicMock()
            mock_gs.return_value = mock_s
            mock_s.vision.ocr_engine = "easyocr"
            mock_s.vision.ocr_languages = ["en"]
            mock_s.vision.ocr_confidence_threshold = 0.5
            tool._easyocr_reader = MagicMock()
            tool._easyocr_reader.readtext.return_value = fake_results
            tool._reader_langs = ["en"]

            result = await tool.extract(img, engine="easyocr")
            assert result.engine_used == "easyocr"
            assert len(result.blocks) == 2
            assert result.blocks[0].text == "Submit"
            assert result.blocks[0].bbox["width"] == 40

    @pytest.mark.asyncio
    async def test_confidence_threshold_filtering(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50), color="white")

        fake_data = {
            "text": ["Clear", "Faint"],
            "conf": [90.0, 30.0],  # 30% = 0.30, below threshold
            "left": [10, 60],
            "top": [5, 5],
            "width": [40, 40],
            "height": [20, 20],
        }

        with patch("nobla.tools.vision.ocr.pytesseract") as mock_tess, \
             patch("nobla.tools.vision.ocr.settings") as mock_s:
            mock_s.vision.ocr_engine = "tesseract"
            mock_s.vision.ocr_languages = ["en"]
            mock_s.vision.ocr_confidence_threshold = 0.5
            mock_tess.image_to_data.return_value = fake_data
            mock_tess.Output.DICT = "dict"

            result = await tool.extract(img)
            assert len(result.blocks) == 1
            assert result.blocks[0].text == "Clear"

    @pytest.mark.asyncio
    async def test_fallback_tesseract_to_easyocr(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50), color="white")

        with patch("nobla.tools.vision.ocr.pytesseract", None), \
             patch("nobla.tools.vision.ocr.settings") as mock_s:
            mock_s.vision.ocr_engine = "tesseract"
            mock_s.vision.ocr_languages = ["en"]
            mock_s.vision.ocr_confidence_threshold = 0.5
            tool._easyocr_reader = MagicMock()
            tool._easyocr_reader.readtext.return_value = [
                ([[0, 0], [50, 0], [50, 20], [0, 20]], "Fallback", 0.8),
            ]
            tool._reader_langs = ["en"]

            result = await tool.extract(img)
            assert result.engine_used == "easyocr"
            assert result.blocks[0].text == "Fallback"

    @pytest.mark.asyncio
    async def test_both_engines_missing_raises(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50), color="white")

        with patch("nobla.tools.vision.ocr.pytesseract", None), \
             patch("nobla.tools.vision.ocr.easyocr_module", None), \
             patch("nobla.tools.vision.ocr.settings") as mock_s:
            mock_s.vision.ocr_engine = "tesseract"
            mock_s.vision.ocr_languages = ["en"]
            mock_s.vision.ocr_confidence_threshold = 0.5

            with pytest.raises(RuntimeError, match="No OCR engine"):
                await tool.extract(img)

    @pytest.mark.asyncio
    async def test_describe_action(self):
        tool = OCRTool()
        params = _make_params({"image_b64": "abc"})
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_s = MagicMock()
            mock_gs.return_value = mock_s
            mock_s.vision.ocr_engine = "tesseract"
            mock_s.vision.ocr_languages = ["en", "ara"]
            desc = tool.describe_action(params)
            assert "tesseract" in desc.lower()
            assert "en" in desc
            assert "ara" in desc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_vision_ocr.py -v`
Expected: FAIL — `ocr.py` does not exist.

- [ ] **Step 3: Implement ocr.py**

```python
# backend/nobla/tools/vision/ocr.py
"""OCRTool — text extraction with Tesseract + EasyOCR fallback."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, asdict
from io import BytesIO

from PIL import Image

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore[assignment]

try:
    import easyocr as easyocr_module
except ImportError:
    easyocr_module = None  # type: ignore[assignment]


@dataclass
class TextBlock:
    text: str
    confidence: float
    bbox: dict  # {x, y, width, height}


@dataclass
class OCRResult:
    blocks: list[TextBlock]
    full_text: str
    engine_used: str


@register_tool
class OCRTool(BaseTool):
    name = "ocr.extract"
    description = "Extract text from a screenshot using OCR"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    def __init__(self):
        super().__init__()
        self._easyocr_reader = None
        self._reader_langs: list[str] | None = None

    async def validate(self, params: ToolParams) -> None:
        if not get_settings().vision.enabled:
            raise ValueError("Vision tools disabled in settings")
        if "image_b64" not in params.args:
            raise ValueError("Missing required parameter: image_b64")

    def describe_action(self, params: ToolParams) -> str:
        engine = params.args.get("engine", get_settings().vision.ocr_engine)
        langs = params.args.get("languages", get_settings().vision.ocr_languages)
        return f"Extract text using {engine} (languages: {', '.join(langs)})"

    async def extract(
        self,
        image: Image.Image,
        languages: list[str] | None = None,
        engine: str | None = None,
    ) -> OCRResult:
        """Internal API — accepts PIL.Image, returns structured OCRResult."""
        languages = languages or get_settings().vision.ocr_languages
        preferred = engine or get_settings().vision.ocr_engine
        other = "easyocr" if preferred == "tesseract" else "tesseract"

        engines = {
            "tesseract": self._tesseract_extract,
            "easyocr": self._easyocr_extract,
        }

        # Try preferred engine first
        try:
            return await engines[preferred](image, languages)
        except (ImportError, TypeError, Exception):
            pass

        # Fall back to the other engine
        try:
            return await engines[other](image, languages)
        except (ImportError, TypeError, Exception):
            pass

        raise RuntimeError(
            "No OCR engine available. Install pytesseract or easyocr: "
            "pip install nobla[vision] or pip install nobla[vision-full]"
        )

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        try:
            image = self._decode_b64(args["image_b64"])
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid image: {e}")

        languages = args.get("languages")
        engine = args.get("engine")

        try:
            result = await self.extract(image, languages, engine)
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))

        return ToolResult(
            success=True,
            data={
                "blocks": [asdict(b) for b in result.blocks],
                "full_text": result.full_text,
                "engine_used": result.engine_used,
            },
        )

    async def _tesseract_extract(
        self, image: Image.Image, languages: list[str]
    ) -> OCRResult:
        if pytesseract is None:
            raise ImportError("pytesseract not installed")

        lang_str = "+".join(languages)
        threshold = get_settings().vision.ocr_confidence_threshold

        data = await asyncio.to_thread(
            pytesseract.image_to_data,
            image,
            output_type=pytesseract.Output.DICT,
            lang=lang_str,
        )

        blocks: list[TextBlock] = []
        for i, text in enumerate(data["text"]):
            if not text.strip():
                continue
            conf = float(data["conf"][i])
            if conf < threshold * 100:  # Tesseract uses 0-100
                continue
            blocks.append(
                TextBlock(
                    text=text.strip(),
                    confidence=conf / 100.0,
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
        if easyocr_module is None:
            raise ImportError("easyocr not installed")

        import numpy  # lazy import — only with vision-full deps (after guard)

        reader = await self._get_reader(languages)
        threshold = get_settings().vision.ocr_confidence_threshold

        results = await asyncio.to_thread(
            reader.readtext, numpy.array(image)
        )

        blocks: list[TextBlock] = []
        for bbox_points, text, confidence in results:
            if confidence < threshold:
                continue
            x1, y1 = bbox_points[0]
            x2, y2 = bbox_points[2]
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=confidence,
                    bbox={
                        "x": int(x1),
                        "y": int(y1),
                        "width": int(x2 - x1),
                        "height": int(y2 - y1),
                    },
                )
            )

        full_text = " ".join(b.text for b in blocks)
        return OCRResult(blocks=blocks, full_text=full_text, engine_used="easyocr")

    async def _get_reader(self, languages: list[str]):
        if self._easyocr_reader is None or self._reader_langs != languages:
            self._easyocr_reader = await asyncio.to_thread(
                easyocr_module.Reader, languages, gpu=False
            )
            self._reader_langs = languages
        return self._easyocr_reader

    @staticmethod
    def _decode_b64(image_b64: str) -> Image.Image:
        raw = base64.b64decode(image_b64)
        return Image.open(BytesIO(raw))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_vision_ocr.py -v`
Expected: All passed.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/vision/ocr.py backend/tests/test_vision_ocr.py
git commit -m "feat(vision): add OCRTool with Tesseract + EasyOCR fallback"
```

---

## Task 4: UIDetectionTool

**Files:**
- Create: `backend/nobla/tools/vision/detection.py`
- Create: `backend/tests/test_vision_detection.py`

- [ ] **Step 1: Write failing tests for UIDetectionTool**

```python
# backend/tests/test_vision_detection.py
"""Unit tests for UIDetectionTool."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from PIL import Image

from nobla.tools.models import ToolCategory, ToolParams
from nobla.tools.vision.detection import UIDetectionTool, DetectedElement
from nobla.tools.vision.ocr import TextBlock, OCRResult
from nobla.security.permissions import Tier


def _make_params(args: dict) -> ToolParams:
    state = MagicMock()
    state.tier = Tier.STANDARD
    state.connection_id = "test-conn"
    return ToolParams(args=args, connection_state=state)


def _make_ocr_result(blocks: list[dict]) -> OCRResult:
    return OCRResult(
        blocks=[TextBlock(**b) for b in blocks],
        full_text=" ".join(b["text"] for b in blocks),
        engine_used="tesseract",
    )


class TestUIDetectionToolMetadata:
    def test_tool_metadata(self):
        tool = UIDetectionTool()
        assert tool.name == "ui.detect_elements"
        assert tool.category == ToolCategory.VISION
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False


class TestElementClassification:
    def test_url_classified_as_link(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        block = TextBlock(text="https://example.com", confidence=0.9,
                          bbox={"x": 10, "y": 10, "width": 150, "height": 20})
        result = tool._classify_element(img, block)
        assert result == "link"

    def test_colon_suffix_classified_as_label(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        block = TextBlock(text="Name:", confidence=0.9,
                          bbox={"x": 10, "y": 10, "width": 60, "height": 20})
        result = tool._classify_element(img, block)
        assert result == "label"

    def test_short_text_with_background_classified_as_button(self):
        tool = UIDetectionTool()
        # Create image with a blue rectangle (button background)
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        for x in range(20, 80):
            for y in range(10, 40):
                img.putpixel((x, y), (0, 0, 200))
        block = TextBlock(text="OK", confidence=0.9,
                          bbox={"x": 20, "y": 10, "width": 60, "height": 30})
        result = tool._classify_element(img, block)
        assert result == "button"

    def test_tall_text_classified_as_heading(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        block = TextBlock(text="Welcome to Settings", confidence=0.9,
                          bbox={"x": 10, "y": 5, "width": 180, "height": 35})
        result = tool._classify_element(img, block)
        assert result == "heading"

    def test_default_classified_as_text(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        block = TextBlock(text="Some paragraph content here", confidence=0.9,
                          bbox={"x": 10, "y": 50, "width": 180, "height": 20})
        result = tool._classify_element(img, block)
        assert result == "text"


class TestOCRBasedDetection:
    @pytest.mark.asyncio
    async def test_detect_returns_elements(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))

        ocr_result = _make_ocr_result([
            {"text": "Submit", "confidence": 0.9,
             "bbox": {"x": 10, "y": 10, "width": 60, "height": 20}},
            {"text": "Name:", "confidence": 0.85,
             "bbox": {"x": 10, "y": 50, "width": 50, "height": 20}},
        ])

        with patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr
            with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
                mock_s = MagicMock()
                mock_gs.return_value = mock_s
                mock_s.vision.ui_tars_enabled = False
                mock_s.vision.detection_confidence_threshold = 0.3

                elements = await tool.detect(img)
                assert len(elements) >= 1
                assert all(isinstance(e, DetectedElement) for e in elements)

    @pytest.mark.asyncio
    async def test_confidence_discounted(self):
        """OCR-detected elements get confidence * 0.7 discount."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))

        ocr_result = _make_ocr_result([
            {"text": "https://link.com", "confidence": 1.0,
             "bbox": {"x": 10, "y": 10, "width": 100, "height": 20}},
        ])

        with patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr
            with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
                mock_s = MagicMock()
                mock_gs.return_value = mock_s
                mock_s.vision.ui_tars_enabled = False
                mock_s.vision.detection_confidence_threshold = 0.0

                elements = await tool.detect(img)
                assert elements[0].confidence == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_threshold_filtering(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))

        ocr_result = _make_ocr_result([
            {"text": "OK", "confidence": 0.3,  # 0.3 * 0.7 = 0.21 < 0.4
             "bbox": {"x": 10, "y": 10, "width": 30, "height": 20}},
        ])

        with patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr
            with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
                mock_s = MagicMock()
                mock_gs.return_value = mock_s
                mock_s.vision.ui_tars_enabled = False
                mock_s.vision.detection_confidence_threshold = 0.4

                elements = await tool.detect(img)
                assert len(elements) == 0


class TestUITarsStub:
    @pytest.mark.asyncio
    async def test_uitars_stub_falls_back_to_ocr(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))

        ocr_result = _make_ocr_result([
            {"text": "Fallback", "confidence": 0.9,
             "bbox": {"x": 10, "y": 10, "width": 80, "height": 20}},
        ])

        with patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr
            with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
                mock_s = MagicMock()
                mock_gs.return_value = mock_s
                mock_s.vision.ui_tars_enabled = True
                mock_s.vision.ui_tars_model_path = ""
                mock_s.vision.detection_confidence_threshold = 0.0

                elements = await tool.detect(img)
                assert len(elements) >= 1


class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_detect_writes_to_cache(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))

        ocr_result = _make_ocr_result([
            {"text": "Cached", "confidence": 0.9,
             "bbox": {"x": 10, "y": 10, "width": 60, "height": 20}},
        ])

        with patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr
            with patch("nobla.tools.vision.detection.settings") as mock_s, \
                 patch("nobla.tools.vision.detection.element_cache") as mock_cache:
                mock_s.vision.ui_tars_enabled = False
                mock_s.vision.detection_confidence_threshold = 0.0

                await tool.detect(img)
                mock_cache.put.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_vision_detection.py -v`
Expected: FAIL — `detection.py` does not exist.

- [ ] **Step 3: Implement detection.py**

```python
# backend/nobla/tools/vision/detection.py
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
                "method": "ui_tars" if settings.vision.ui_tars_enabled else "ocr_heuristic",
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

        # URL pattern → link
        if text.startswith(("http://", "https://", "www.")):
            return "link"

        # Label pattern (ends with ":")
        if text.endswith(":"):
            return "label"

        # Short text with distinct background → button
        has_bg = self._has_distinct_background(image, bbox)
        word_count = len(text.split())
        if word_count <= 3 and has_bg:
            return "button"

        # Tall text → heading
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_vision_detection.py -v`
Expected: All passed.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/vision/detection.py backend/tests/test_vision_detection.py
git commit -m "feat(vision): add UIDetectionTool with OCR heuristics + UI-TARS stub"
```

---

## Task 5: ElementTargetingTool

**Files:**
- Create: `backend/nobla/tools/vision/targeting.py`
- Create: `backend/tests/test_vision_targeting.py`

- [ ] **Step 1: Write failing tests for ElementTargetingTool**

```python
# backend/tests/test_vision_targeting.py
"""Unit tests for ElementTargetingTool."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from PIL import Image

from nobla.tools.models import ToolCategory, ToolParams
from nobla.tools.vision.targeting import ElementTargetingTool, TargetResult, _Match
from nobla.tools.vision.detection import DetectedElement
from nobla.tools.vision.capture import CaptureResult
from nobla.security.permissions import Tier


def _make_params(args: dict) -> ToolParams:
    state = MagicMock()
    state.tier = Tier.STANDARD
    state.connection_id = "test-conn"
    return ToolParams(args=args, connection_state=state)


def _make_elements() -> list[DetectedElement]:
    return [
        DetectedElement("button", "Submit", {"x": 100, "y": 200, "width": 80, "height": 30}, 0.9),
        DetectedElement("button", "Cancel", {"x": 200, "y": 200, "width": 80, "height": 30}, 0.85),
        DetectedElement("label", "Name:", {"x": 10, "y": 100, "width": 50, "height": 20}, 0.8),
        DetectedElement("heading", "Settings", {"x": 10, "y": 10, "width": 150, "height": 35}, 0.95),
        DetectedElement("link", "https://help.com", {"x": 10, "y": 300, "width": 120, "height": 20}, 0.75),
    ]


class TestElementTargetingToolMetadata:
    def test_tool_metadata(self):
        tool = ElementTargetingTool()
        assert tool.name == "ui.target_element"
        assert tool.category == ToolCategory.VISION
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False


class TestKeywordExtraction:
    def test_removes_stopwords(self):
        tool = ElementTargetingTool()
        keywords = tool._extract_keywords("the big Submit button")
        assert "the" not in keywords
        assert "big" not in keywords
        assert "submit" in keywords
        assert "button" in keywords

    def test_empty_after_stopwords(self):
        tool = ElementTargetingTool()
        keywords = tool._extract_keywords("the a an")
        assert keywords == []

    def test_preserves_meaningful_words(self):
        tool = ElementTargetingTool()
        keywords = tool._extract_keywords("Save Changes")
        assert keywords == ["save", "changes"]


class TestFuzzyMatching:
    def test_exact_match_high_score(self):
        tool = ElementTargetingTool()
        elements = _make_elements()
        match = tool._best_match("Submit button", elements)
        assert match is not None
        assert match.element.label == "Submit"
        assert match.score > 0.5

    def test_partial_match(self):
        tool = ElementTargetingTool()
        elements = _make_elements()
        match = tool._best_match("Cancel", elements)
        assert match is not None
        assert match.element.label == "Cancel"

    def test_type_bonus(self):
        """'button' in description gives bonus to button-type elements."""
        tool = ElementTargetingTool()
        elements = _make_elements()
        match_with_type = tool._best_match("Submit button", elements)
        match_without_type = tool._best_match("Submit", elements)
        # Both should match Submit, but with_type should score higher
        assert match_with_type is not None
        assert match_without_type is not None
        assert match_with_type.element.label == "Submit"

    def test_no_match_returns_none(self):
        tool = ElementTargetingTool()
        elements = _make_elements()
        match = tool._best_match("nonexistent element xyz", elements)
        assert match is None

    def test_keyword_dilution_prevention(self):
        """'submit form' should still match 'Submit' despite 'form' not matching."""
        tool = ElementTargetingTool()
        elements = _make_elements()
        match = tool._best_match("submit form", elements)
        assert match is not None
        assert match.element.label == "Submit"

    def test_fuzzy_typo_matching(self):
        """'Submitt' should fuzzy-match 'Submit'."""
        tool = ElementTargetingTool()
        elements = _make_elements()
        match = tool._best_match("Submitt", elements)
        assert match is not None
        assert match.element.label == "Submit"


class TestTargetComposition:
    @pytest.mark.asyncio
    async def test_target_returns_center_coordinates(self):
        tool = ElementTargetingTool()
        img = Image.new("RGB", (400, 400), color="white")
        capture_result = CaptureResult(image=img, width=400, height=400, monitor=0)
        elements = _make_elements()

        with patch.object(tool, "_capture", new_callable=lambda: property(lambda self: MagicMock(
            capture=AsyncMock(return_value=capture_result)
        ))):
            with patch.object(tool, "_detector", new_callable=lambda: property(lambda self: MagicMock(
                detect=AsyncMock(return_value=elements)
            ))):
                with patch("nobla.tools.vision.targeting.element_cache") as mock_cache:
                    mock_cache.get.return_value = None

                    result = await tool.target("Submit button")
                    assert isinstance(result, TargetResult)
                    # Submit button bbox: x=100, y=200, w=80, h=30
                    # Center: (140, 215)
                    assert result.x == 140
                    assert result.y == 215

    @pytest.mark.asyncio
    async def test_target_uses_cache(self):
        tool = ElementTargetingTool()
        img = Image.new("RGB", (400, 400), color="white")
        capture_result = CaptureResult(image=img, width=400, height=400, monitor=0)
        cached_elements = [
            {"element_type": "button", "label": "Cached", "bbox": {"x": 50, "y": 50, "width": 100, "height": 40}, "confidence": 0.9},
        ]

        with patch.object(tool, "_capture", new_callable=lambda: property(lambda self: MagicMock(
            capture=AsyncMock(return_value=capture_result)
        ))):
            with patch.object(tool, "_detector") as mock_detector:
                with patch("nobla.tools.vision.targeting.element_cache") as mock_cache:
                    mock_cache.get.return_value = cached_elements

                    result = await tool.target("Cached button")
                    assert result.element.label == "Cached"
                    # detector.detect should NOT be called — cache hit
                    mock_detector.detect.assert_not_called()

    @pytest.mark.asyncio
    async def test_target_no_match_raises(self):
        tool = ElementTargetingTool()
        img = Image.new("RGB", (400, 400), color="white")
        capture_result = CaptureResult(image=img, width=400, height=400, monitor=0)

        with patch.object(tool, "_capture", new_callable=lambda: property(lambda self: MagicMock(
            capture=AsyncMock(return_value=capture_result)
        ))):
            with patch.object(tool, "_detector", new_callable=lambda: property(lambda self: MagicMock(
                detect=AsyncMock(return_value=[])
            ))):
                with patch("nobla.tools.vision.targeting.element_cache") as mock_cache:
                    mock_cache.get.return_value = None

                    with pytest.raises(ValueError, match="No element"):
                        await tool.target("nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_vision_targeting.py -v`
Expected: FAIL — `targeting.py` does not exist.

- [ ] **Step 3: Implement targeting.py**

```python
# backend/nobla/tools/vision/targeting.py
"""ElementTargetingTool — natural language description → screen coordinates."""
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
        description = args["description"]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_vision_targeting.py -v`
Expected: All passed.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/vision/targeting.py backend/tests/test_vision_targeting.py
git commit -m "feat(vision): add ElementTargetingTool with keyword matching"
```

---

## Task 6: Module Wiring & Integration Tests

**Files:**
- Modify: `backend/nobla/tools/vision/__init__.py`
- Modify: `backend/nobla/tools/__init__.py`
- Create: `backend/tests/integration/test_vision_flow.py`

- [ ] **Step 1: Wire vision/__init__.py**

```python
# backend/nobla/tools/vision/__init__.py
"""Vision tools — auto-discovery imports."""

# Import modules to trigger @register_tool decorators.
from nobla.tools.vision import capture  # noqa: F401
from nobla.tools.vision import ocr  # noqa: F401
from nobla.tools.vision import detection  # noqa: F401
from nobla.tools.vision import targeting  # noqa: F401

# element_cache singleton lives in cache.py — import directly:
#   from nobla.tools.vision.cache import element_cache
```

- [ ] **Step 2: Wire tools/__init__.py**

Read `backend/nobla/tools/__init__.py` and add the vision import. Add after existing imports:

```python
from nobla.tools import vision  # noqa: F401
```

- [ ] **Step 3: Run all existing tests to ensure no regressions**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration`
Expected: All existing tests still pass (51+ from Phase 4-Pre + new vision tests).

**Note:** Vision tools now appear in the registry baseline. Any existing tests in `test_tool_registry.py` that assert exact tool counts (e.g., `assert len(tools) == N`) must be updated to account for the 4 new vision tools.

- [ ] **Step 4: Write integration tests**

```python
# backend/tests/integration/test_vision_flow.py
"""Integration tests for vision tools via WebSocket."""
from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from tests.integration.conftest import RpcClient


def _make_test_image_b64() -> str:
    img = Image.new("RGB", (200, 100), color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.integration
class TestVisionToolList:
    @pytest.mark.asyncio
    async def test_vision_tools_in_list(self, authenticated_client: RpcClient):
        """All 4 vision tools appear in tool.list for STANDARD tier."""
        result = await authenticated_client.call_expect_result(
            "tool.list", {"category": "vision"}
        )
        tool_names = [t["name"] for t in result["tools"]]
        assert "screenshot.capture" in tool_names
        assert "ocr.extract" in tool_names
        assert "ui.detect_elements" in tool_names
        assert "ui.target_element" in tool_names

    @pytest.mark.asyncio
    async def test_vision_tools_have_correct_tier(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result(
            "tool.list", {"category": "vision"}
        )
        for tool in result["tools"]:
            assert tool["requires_approval"] is False


@pytest.mark.integration
class TestScreenshotViaWebSocket:
    @pytest.mark.asyncio
    async def test_screenshot_execute(self, authenticated_client: RpcClient):
        """Execute screenshot.capture via WebSocket (mocked mss)."""
        def _fake_grab(rect):
            img = Image.new("RGB", (200, 100), color="blue")
            result = MagicMock()
            result.rgb = img.tobytes()
            result.size = (200, 100)
            result.width = 200
            result.height = 100
            return result

        with patch("nobla.tools.vision.capture.mss_module") as mock_mss:
            mock_ctx = MagicMock()
            mock_ctx.monitors = [
                {"left": 0, "top": 0, "width": 200, "height": 100},
                {"left": 0, "top": 0, "width": 200, "height": 100},
            ]
            mock_ctx.grab = MagicMock(side_effect=_fake_grab)
            mock_mss.mss.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)

            result = await authenticated_client.call_expect_result(
                "tool.execute",
                {"tool_name": "screenshot.capture", "args": {"monitor": 0}},
            )
            assert result["success"] is True
            assert "image_b64" in result["data"]


@pytest.mark.integration
class TestOCRViaWebSocket:
    @pytest.mark.asyncio
    async def test_ocr_execute(self, authenticated_client: RpcClient):
        """Execute ocr.extract via WebSocket (mocked Tesseract)."""
        image_b64 = _make_test_image_b64()

        fake_data = {
            "text": ["Hello"],
            "conf": [95.0],
            "left": [10],
            "top": [5],
            "width": [40],
            "height": [20],
        }

        with patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_tess.image_to_data.return_value = fake_data
            mock_tess.Output.DICT = "dict"

            result = await authenticated_client.call_expect_result(
                "tool.execute",
                {"tool_name": "ocr.extract", "args": {"image_b64": image_b64}},
            )
            assert result["success"] is True
            assert result["data"]["full_text"] == "Hello"


@pytest.mark.integration
class TestVisionPermissions:
    @pytest.mark.asyncio
    async def test_safe_tier_cannot_access_vision(self, ws_client):
        """SAFE tier (tier=1) cannot use STANDARD vision tools."""
        # Register with SAFE tier
        await ws_client.call_expect_result(
            "system.register", {"client_type": "flutter", "tier": 1}
        )
        error = await ws_client.call_expect_error(
            "tool.execute",
            {"tool_name": "screenshot.capture", "args": {}},
        )
        assert error["code"] == -32042 or "permission" in error["message"].lower()
```

- [ ] **Step 5: Run integration tests**

Run: `cd backend && python -m pytest tests/integration/test_vision_flow.py -v`
Expected: All passed.

- [ ] **Step 6: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass (51 existing + ~35 new vision tests).

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/tools/vision/__init__.py backend/nobla/tools/__init__.py backend/tests/integration/test_vision_flow.py
git commit -m "feat(vision): wire auto-discovery + integration tests

All 4 vision tools registered and accessible via tool.execute RPC.
Integration tests verify WebSocket flow and permission enforcement."
```

---

## Summary

| Task | Files | Tests | Description |
|------|-------|-------|-------------|
| 0 | 2 modified, 1 created | 3 | VisionSettings + dependencies |
| 1 | 2 created | 8 | ElementCache + hash_thumbnail |
| 2 | 1 created | 8 | ScreenshotTool (mss capture) |
| 3 | 1 created | 7 | OCRTool (Tesseract + EasyOCR fallback) |
| 4 | 1 created | 8 | UIDetectionTool (heuristics + UI-TARS stub) |
| 5 | 1 created | 9 | ElementTargetingTool (NL → coordinates) |
| 6 | 2 modified, 1 created | 4 | Module wiring + integration tests |
| **Total** | **11 files** | **~47 tests** | |

**Execution order:** Tasks 0-6 are sequential — each builds on the previous. Task 0 must complete first (settings). Tasks 1-5 are the core tools in dependency order. Task 6 wires everything together.

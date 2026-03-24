"""Tests for UIDetectionTool — OCR heuristics + UI-TARS stub."""
from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from nobla.tools.models import ToolCategory, ToolParams
from nobla.security.permissions import Tier
from nobla.tools.vision.ocr import OCRResult, TextBlock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(args: dict) -> ToolParams:
    cs = MagicMock()
    return ToolParams(args=args, connection_state=cs)


def _dummy_b64(width: int = 100, height: int = 50, color=(255, 255, 255)) -> str:
    """Return a valid PNG as base64."""
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _make_settings(
    enabled: bool = True,
    ui_tars_enabled: bool = False,
    ui_tars_model_path: str = "",
    threshold: float = 0.3,
) -> MagicMock:
    s = MagicMock()
    s.vision.enabled = enabled
    s.vision.ui_tars_enabled = ui_tars_enabled
    s.vision.ui_tars_model_path = ui_tars_model_path
    s.vision.detection_confidence_threshold = threshold
    return s


def _make_ocr_result(blocks: list[TextBlock]) -> OCRResult:
    full_text = " ".join(b.text for b in blocks)
    return OCRResult(blocks=blocks, full_text=full_text, engine_used="tesseract")


def _block(text: str, confidence: float = 0.9,
           x: int = 10, y: int = 10, width: int = 40, height: int = 20) -> TextBlock:
    return TextBlock(
        text=text,
        confidence=confidence,
        bbox={"x": x, "y": y, "width": width, "height": height},
    )


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from nobla.tools.vision.detection import UIDetectionTool, DetectedElement


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

class TestUIDetectionToolMetadata:
    def test_name(self):
        tool = UIDetectionTool()
        assert tool.name == "ui.detect_elements"

    def test_category(self):
        tool = UIDetectionTool()
        assert tool.category == ToolCategory.VISION

    def test_tier(self):
        tool = UIDetectionTool()
        assert tool.tier == Tier.STANDARD

    def test_requires_no_approval(self):
        tool = UIDetectionTool()
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# validate() tests
# ---------------------------------------------------------------------------

class TestUIDetectionToolValidate:
    @pytest.mark.asyncio
    async def test_validate_raises_when_vision_disabled(self):
        tool = UIDetectionTool()
        with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=False)
            with pytest.raises(ValueError, match="Vision tools disabled"):
                await tool.validate(_make_params({"image_b64": _dummy_b64()}))

    @pytest.mark.asyncio
    async def test_validate_raises_when_no_image_b64(self):
        tool = UIDetectionTool()
        with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=True)
            with pytest.raises(ValueError, match="image_b64"):
                await tool.validate(_make_params({}))

    @pytest.mark.asyncio
    async def test_validate_passes_with_valid_params(self):
        tool = UIDetectionTool()
        with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=True)
            # Should not raise
            await tool.validate(_make_params({"image_b64": _dummy_b64()}))


# ---------------------------------------------------------------------------
# describe_action() tests
# ---------------------------------------------------------------------------

class TestUIDetectionToolDescribeAction:
    def test_describe_action_returns_string(self):
        tool = UIDetectionTool()
        desc = tool.describe_action(_make_params({"image_b64": _dummy_b64()}))
        assert isinstance(desc, str)
        assert len(desc) > 0


# ---------------------------------------------------------------------------
# _classify_element() tests
# ---------------------------------------------------------------------------

class TestClassifyElement:
    """5 classification tests: link, label, button, heading, text."""

    def _tool(self):
        return UIDetectionTool()

    def _white_image(self, w=200, h=200):
        return Image.new("RGB", (w, h), color=(255, 255, 255))

    def test_url_text_classified_as_link(self):
        tool = self._tool()
        img = self._white_image()
        block = _block("https://example.com", x=10, y=10, width=120, height=15)
        result = tool._classify_element(img, block)
        assert result == "link"

    def test_url_http_classified_as_link(self):
        tool = self._tool()
        img = self._white_image()
        block = _block("http://example.com/path", x=10, y=10, width=120, height=15)
        result = tool._classify_element(img, block)
        assert result == "link"

    def test_www_url_classified_as_link(self):
        tool = self._tool()
        img = self._white_image()
        block = _block("www.example.com", x=10, y=10, width=100, height=15)
        result = tool._classify_element(img, block)
        assert result == "link"

    def test_text_ending_with_colon_classified_as_label(self):
        tool = self._tool()
        img = self._white_image()
        block = _block("Username:", x=10, y=10, width=70, height=15)
        result = tool._classify_element(img, block)
        assert result == "label"

    def test_short_text_with_distinct_background_classified_as_button(self):
        tool = self._tool()
        # Create image with a blue rectangle exactly at bbox coords (no extra margin),
        # so outside samples (pad=4 beyond bbox edge) land on white background.
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # bbox: x=50, y=80, width=60, height=25 → fill exactly [50,80,110,105]
        draw.rectangle([50, 80, 110, 105], fill=(0, 0, 255))
        block = _block("Submit", x=50, y=80, width=60, height=25)
        result = tool._classify_element(img, block)
        assert result == "button"

    def test_tall_text_classified_as_heading(self):
        tool = self._tool()
        img = self._white_image()
        # height > 30 and not a button (no distinct bg on white image)
        block = _block("Welcome Header", x=10, y=10, width=150, height=40)
        result = tool._classify_element(img, block)
        assert result == "heading"

    def test_default_text_classification(self):
        tool = self._tool()
        img = self._white_image()
        # Plain text on white bg, small height, not URL/label
        block = _block("Some plain text here with many words", x=10, y=10, width=200, height=15)
        result = tool._classify_element(img, block)
        assert result == "text"


# ---------------------------------------------------------------------------
# _has_distinct_background() tests
# ---------------------------------------------------------------------------

class TestHasDistinctBackground:
    def test_uniform_white_image_returns_false(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        block = _block("text", x=50, y=50, width=60, height=20)
        assert tool._has_distinct_background(img, block.bbox) is False

    def test_colored_rectangle_returns_true(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Fill exactly the bbox [50,50,110,70] so outside samples (pad=4) land on white
        draw.rectangle([50, 50, 110, 70], fill=(0, 100, 200))
        block = _block("text", x=50, y=50, width=60, height=20)
        assert tool._has_distinct_background(img, block.bbox) is True

    def test_out_of_bounds_bbox_returns_false(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        # bbox completely outside image
        bbox = {"x": 500, "y": 500, "width": 100, "height": 100}
        result = tool._has_distinct_background(img, bbox)
        assert result is False


# ---------------------------------------------------------------------------
# OCR-based detection tests
# ---------------------------------------------------------------------------

class TestOCRBasedDetect:
    @pytest.mark.asyncio
    async def test_ocr_based_detect_returns_elements(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Click me", confidence=0.9, width=60, height=20),
            _block("Username:", confidence=0.95, width=80, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_s = _make_settings(threshold=0.3)
            mock_gs.return_value = mock_s

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        assert len(elements) == 2
        assert all(isinstance(e, DetectedElement) for e in elements)

    @pytest.mark.asyncio
    async def test_ocr_tool_not_available_raises_runtime_error(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (100, 50))

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.3)
            mock_get_ocr.return_value = None

            with pytest.raises(RuntimeError, match="OCR tool not available"):
                await tool._ocr_based_detect(img)

    @pytest.mark.asyncio
    async def test_ocr_based_detect_element_types_are_set(self):
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Username:", confidence=0.9, width=70, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.3)
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        assert elements[0].element_type == "label"
        assert elements[0].label == "Username:"


# ---------------------------------------------------------------------------
# Confidence discount tests
# ---------------------------------------------------------------------------

class TestConfidenceDiscount:
    @pytest.mark.asyncio
    async def test_ocr_confidence_discounted_by_0_7(self):
        """OCR blocks should have confidence * 0.7 applied."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        original_confidence = 0.9
        ocr_result = _make_ocr_result([
            _block("Hello", confidence=original_confidence, width=50, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.1)
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        expected = round(original_confidence * 0.7, 4)
        assert elements[0].confidence == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_high_ocr_confidence_discounted_correctly(self):
        """1.0 confidence -> 0.7 after discount."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Perfect", confidence=1.0, width=60, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.1)
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        assert elements[0].confidence == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Threshold filtering tests
# ---------------------------------------------------------------------------

class TestThresholdFiltering:
    @pytest.mark.asyncio
    async def test_low_confidence_blocks_filtered_out(self):
        """Blocks with discounted confidence below threshold should be excluded."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        # confidence=0.4 * 0.7 = 0.28, below threshold of 0.3
        ocr_result = _make_ocr_result([
            _block("LowConf", confidence=0.4, width=70, height=15),
            _block("HighConf", confidence=0.9, width=70, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.3)
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        # 0.4 * 0.7 = 0.28 < 0.3 -> filtered; 0.9 * 0.7 = 0.63 >= 0.3 -> kept
        assert len(elements) == 1
        assert elements[0].label == "HighConf"

    @pytest.mark.asyncio
    async def test_zero_threshold_keeps_all_blocks(self):
        """threshold=0.0 should keep all blocks regardless of confidence."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("A", confidence=0.1, width=20, height=15),
            _block("B", confidence=0.05, width=20, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(threshold=0.0)
            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool._ocr_based_detect(img)

        assert len(elements) == 2


# ---------------------------------------------------------------------------
# UI-TARS stub tests
# ---------------------------------------------------------------------------

class TestUITARSStub:
    @pytest.mark.asyncio
    async def test_uitars_stub_raises_not_implemented_when_no_model_path(self):
        """_uitars_detect raises NotImplementedError when not configured."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (100, 50))

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(ui_tars_model_path="")
            with pytest.raises((RuntimeError, NotImplementedError)):
                await tool._uitars_detect(img)

    @pytest.mark.asyncio
    async def test_uitars_enabled_but_no_model_path_falls_back_to_ocr(self):
        """When ui_tars_enabled=True but model_path is empty, falls back to OCR."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Fallback text", confidence=0.9, width=100, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_s = _make_settings(
                ui_tars_enabled=True,
                ui_tars_model_path="",
                threshold=0.3,
            )
            mock_gs.return_value = mock_s

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool.detect(img)

        assert len(elements) == 1
        assert elements[0].label == "Fallback text"

    @pytest.mark.asyncio
    async def test_uitars_disabled_uses_ocr(self):
        """When ui_tars_enabled=False, OCR path is used directly."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("OCR only", confidence=0.9, width=80, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr:
            mock_gs.return_value = _make_settings(ui_tars_enabled=False, threshold=0.3)

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            elements = await tool.detect(img)

        assert len(elements) == 1
        assert elements[0].label == "OCR only"


# ---------------------------------------------------------------------------
# Cache integration tests
# ---------------------------------------------------------------------------

class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_detect_writes_to_element_cache(self):
        """detect() should call element_cache.put after successful detection."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Cached", confidence=0.9, width=60, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache") as mock_cache:
            mock_gs.return_value = _make_settings(threshold=0.3)

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            await tool.detect(img)

        mock_cache.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_cache_put_receives_dict_list(self):
        """element_cache.put should receive a list of dicts, not DetectedElement objects."""
        tool = UIDetectionTool()
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        ocr_result = _make_ocr_result([
            _block("Test", confidence=0.9, width=50, height=15),
        ])

        captured_call = {}

        def capture_put(key, elements):
            captured_call["key"] = key
            captured_call["elements"] = elements

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache") as mock_cache:
            mock_gs.return_value = _make_settings(threshold=0.3)
            mock_cache.put.side_effect = capture_put

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            await tool.detect(img)

        assert "elements" in captured_call
        assert isinstance(captured_call["elements"], list)
        if captured_call["elements"]:
            assert isinstance(captured_call["elements"][0], dict)


# ---------------------------------------------------------------------------
# execute() tests
# ---------------------------------------------------------------------------

class TestUIDetectionToolExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_elements_on_valid_image(self):
        tool = UIDetectionTool()
        b64 = _dummy_b64(200, 100)
        ocr_result = _make_ocr_result([
            _block("Hello", confidence=0.9, width=50, height=15),
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache"):
            mock_gs.return_value = _make_settings(threshold=0.3)

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            result = await tool.execute(_make_params({"image_b64": b64}))

        assert result.success is True
        assert "elements" in result.data
        assert "count" in result.data
        assert "method" in result.data

    @pytest.mark.asyncio
    async def test_execute_returns_error_on_invalid_b64(self):
        tool = UIDetectionTool()
        with patch("nobla.tools.vision.detection.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings()
            result = await tool.execute(_make_params({"image_b64": "!!notbase64!!"}))

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_filters_by_element_types(self):
        """element_types filter in args should restrict returned elements."""
        tool = UIDetectionTool()
        b64 = _dummy_b64(200, 100)
        ocr_result = _make_ocr_result([
            _block("Username:", confidence=0.9, width=70, height=15),  # label
            _block("https://example.com", confidence=0.9, width=120, height=15),  # link
        ])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache"):
            mock_gs.return_value = _make_settings(threshold=0.3)

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            result = await tool.execute(_make_params({
                "image_b64": b64,
                "element_types": ["link"],
            }))

        assert result.success is True
        types = [e["element_type"] for e in result.data["elements"]]
        assert all(t == "link" for t in types)

    @pytest.mark.asyncio
    async def test_execute_method_field_is_ocr_heuristic_by_default(self):
        tool = UIDetectionTool()
        b64 = _dummy_b64(200, 100)
        ocr_result = _make_ocr_result([])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache"):
            mock_s = _make_settings(ui_tars_enabled=False, threshold=0.3)
            mock_gs.return_value = mock_s

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            result = await tool.execute(_make_params({"image_b64": b64}))

        assert result.data["method"] == "ocr_heuristic"

    @pytest.mark.asyncio
    async def test_execute_method_field_is_ui_tars_when_enabled(self):
        """When ui_tars_enabled=True (and it falls back), method should be 'ui_tars'."""
        tool = UIDetectionTool()
        b64 = _dummy_b64(200, 100)
        ocr_result = _make_ocr_result([])

        with patch("nobla.tools.vision.detection.get_settings") as mock_gs, \
             patch.object(tool, "_get_ocr_tool") as mock_get_ocr, \
             patch("nobla.tools.vision.detection.element_cache"):
            mock_s = _make_settings(ui_tars_enabled=True, threshold=0.3)
            mock_gs.return_value = mock_s

            mock_ocr = MagicMock()
            mock_ocr.extract = AsyncMock(return_value=ocr_result)
            mock_get_ocr.return_value = mock_ocr

            result = await tool.execute(_make_params({"image_b64": b64}))

        assert result.data["method"] == "ui_tars"

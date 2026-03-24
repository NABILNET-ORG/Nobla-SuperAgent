"""Tests for OCRTool — Tesseract + EasyOCR fallback."""
from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from nobla.tools.models import ToolCategory, ToolParams
from nobla.security.permissions import Tier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(args: dict) -> ToolParams:
    cs = MagicMock()
    return ToolParams(args=args, connection_state=cs)


def _dummy_b64() -> str:
    """Return a valid 1×1 white PNG as base64."""
    img = Image.new("RGB", (10, 10), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _make_settings(enabled: bool = True, engine: str = "tesseract",
                   threshold: float = 0.5) -> MagicMock:
    s = MagicMock()
    s.vision.enabled = enabled
    s.vision.ocr_engine = engine
    s.vision.ocr_languages = ["en"]
    s.vision.ocr_confidence_threshold = threshold
    return s


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from nobla.tools.vision.ocr import OCRTool, OCRResult, TextBlock


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

class TestOCRToolMetadata:
    def test_name(self):
        tool = OCRTool()
        assert tool.name == "ocr.extract"

    def test_category(self):
        tool = OCRTool()
        assert tool.category == ToolCategory.VISION

    def test_tier(self):
        tool = OCRTool()
        assert tool.tier == Tier.STANDARD

    def test_requires_no_approval(self):
        tool = OCRTool()
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# validate() tests
# ---------------------------------------------------------------------------

class TestOCRToolValidate:
    @pytest.mark.asyncio
    async def test_validate_raises_when_vision_disabled(self):
        tool = OCRTool()
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=False)
            with pytest.raises(ValueError, match="Vision tools disabled"):
                await tool.validate(_make_params({"image_b64": _dummy_b64()}))

    @pytest.mark.asyncio
    async def test_validate_raises_when_no_image_b64(self):
        tool = OCRTool()
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=True)
            with pytest.raises(ValueError, match="image_b64"):
                await tool.validate(_make_params({}))

    @pytest.mark.asyncio
    async def test_validate_passes_with_valid_params(self):
        tool = OCRTool()
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(enabled=True)
            # Should not raise
            await tool.validate(_make_params({"image_b64": _dummy_b64()}))


# ---------------------------------------------------------------------------
# describe_action() tests
# ---------------------------------------------------------------------------

class TestOCRToolDescribeAction:
    def test_describe_action_includes_engine_and_languages(self):
        tool = OCRTool()
        params = _make_params({
            "image_b64": _dummy_b64(),
            "engine": "tesseract",
            "languages": ["en", "fr"],
        })
        desc = tool.describe_action(params)
        assert "tesseract" in desc
        assert "en" in desc
        assert "fr" in desc

    def test_describe_action_uses_defaults_when_not_specified(self):
        tool = OCRTool()
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(engine="easyocr")
            params = _make_params({"image_b64": _dummy_b64()})
            desc = tool.describe_action(params)
            assert "easyocr" in desc


# ---------------------------------------------------------------------------
# _tesseract_extract() tests
# ---------------------------------------------------------------------------

class TestTesseractExtract:
    @pytest.mark.asyncio
    async def test_tesseract_returns_text_blocks(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        tess_data = {
            "text": ["Hello", "World", ""],
            "conf": [90, 80, -1],
            "left": [0, 50, 0],
            "top": [0, 0, 0],
            "width": [40, 40, 0],
            "height": [20, 20, 0],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool._tesseract_extract(img, ["en"])

        assert isinstance(result, OCRResult)
        assert result.engine_used == "tesseract"
        # "Hello" conf=90/100=0.9 >= 0.5, "World" conf=80/100=0.8 >= 0.5
        assert len(result.blocks) == 2
        texts = [b.text for b in result.blocks]
        assert "Hello" in texts
        assert "World" in texts

    @pytest.mark.asyncio
    async def test_tesseract_filters_low_confidence(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        tess_data = {
            "text": ["Good", "Bad", ""],
            "conf": [90, 30, -1],
            "left": [0, 50, 0],
            "top": [0, 0, 0],
            "width": [40, 40, 0],
            "height": [20, 20, 0],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool._tesseract_extract(img, ["en"])

        # Only "Good" passes (0.9 >= 0.5); "Bad" fails (0.3 < 0.5)
        assert len(result.blocks) == 1
        assert result.blocks[0].text == "Good"

    @pytest.mark.asyncio
    async def test_tesseract_raises_if_not_installed(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        with patch("nobla.tools.vision.ocr.pytesseract", None):
            with pytest.raises(ImportError):
                await tool._tesseract_extract(img, ["en"])

    @pytest.mark.asyncio
    async def test_tesseract_confidence_scale_0_to_100(self):
        """Tesseract returns conf 0-100; threshold is 0.0-1.0."""
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        tess_data = {
            "text": ["At50", "Below50"],
            "conf": [50, 49],
            "left": [0, 50],
            "top": [0, 0],
            "width": [40, 40],
            "height": [20, 20],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool._tesseract_extract(img, ["en"])

        # 50/100 = 0.5 >= 0.5 passes; 49/100 = 0.49 < 0.5 filtered
        assert len(result.blocks) == 1
        assert result.blocks[0].text == "At50"

    @pytest.mark.asyncio
    async def test_tesseract_full_text_joins_blocks(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        tess_data = {
            "text": ["Hello", "World"],
            "conf": [90, 85],
            "left": [0, 50],
            "top": [0, 0],
            "width": [40, 40],
            "height": [20, 20],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool._tesseract_extract(img, ["en"])

        assert "Hello" in result.full_text
        assert "World" in result.full_text


# ---------------------------------------------------------------------------
# _easyocr_extract() tests
# ---------------------------------------------------------------------------

class TestEasyOCRExtract:
    @pytest.mark.asyncio
    async def test_easyocr_returns_text_blocks(self):
        tool = OCRTool()
        # Pre-set reader so we skip actual easyocr import
        mock_reader = MagicMock()
        tool._easyocr_reader = mock_reader
        tool._reader_langs = ["en"]

        img = Image.new("RGB", (100, 50))
        # easyocr returns: (bbox_points, text, confidence)
        bbox_points = [[10, 5], [50, 5], [50, 25], [10, 25]]
        mock_reader.readtext.return_value = [(bbox_points, "Hello", 0.95)]

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.easyocr_module") as mock_eocr:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_eocr.__bool__ = lambda self: True  # not None

            result = await tool._easyocr_extract(img, ["en"])

        assert isinstance(result, OCRResult)
        assert result.engine_used == "easyocr"
        assert len(result.blocks) == 1
        assert result.blocks[0].text == "Hello"
        assert result.blocks[0].confidence == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_easyocr_bbox_conversion(self):
        """bbox [[x1,y1],[x2,y1],[x2,y2],[x1,y2]] -> {x,y,width,height}."""
        tool = OCRTool()
        mock_reader = MagicMock()
        tool._easyocr_reader = mock_reader
        tool._reader_langs = ["en"]

        img = Image.new("RGB", (100, 50))
        # x1=10, y1=5, x2=50, y2=25 => x=10, y=5, w=40, h=20
        bbox_points = [[10, 5], [50, 5], [50, 25], [10, 25]]
        mock_reader.readtext.return_value = [(bbox_points, "Test", 0.9)]

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.easyocr_module") as _mock_eocr:
            mock_gs.return_value = _make_settings(threshold=0.5)

            result = await tool._easyocr_extract(img, ["en"])

        bbox = result.blocks[0].bbox
        assert bbox["x"] == 10
        assert bbox["y"] == 5
        assert bbox["width"] == 40
        assert bbox["height"] == 20

    @pytest.mark.asyncio
    async def test_easyocr_filters_low_confidence(self):
        tool = OCRTool()
        mock_reader = MagicMock()
        tool._easyocr_reader = mock_reader
        tool._reader_langs = ["en"]

        img = Image.new("RGB", (100, 50))
        bbox = [[0, 0], [40, 0], [40, 20], [0, 20]]
        mock_reader.readtext.return_value = [
            (bbox, "Good", 0.9),
            (bbox, "Bad", 0.3),
        ]

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.easyocr_module") as _mock_eocr:
            mock_gs.return_value = _make_settings(threshold=0.5)

            result = await tool._easyocr_extract(img, ["en"])

        assert len(result.blocks) == 1
        assert result.blocks[0].text == "Good"

    @pytest.mark.asyncio
    async def test_easyocr_raises_if_not_installed(self):
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        with patch("nobla.tools.vision.ocr.easyocr_module", None):
            with pytest.raises(ImportError):
                await tool._easyocr_extract(img, ["en"])


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------

class TestOCRFallback:
    @pytest.mark.asyncio
    async def test_tesseract_to_easyocr_fallback(self):
        """When pytesseract is None, easyocr should be used."""
        tool = OCRTool()
        mock_reader = MagicMock()
        tool._easyocr_reader = mock_reader
        tool._reader_langs = ["en"]

        img = Image.new("RGB", (100, 50))
        bbox = [[0, 0], [40, 0], [40, 20], [0, 20]]
        mock_reader.readtext.return_value = [(bbox, "Fallback", 0.88)]

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract", None), \
             patch("nobla.tools.vision.ocr.easyocr_module") as _mock_eocr:
            mock_gs.return_value = _make_settings(engine="tesseract", threshold=0.5)

            result = await tool.extract(img, languages=["en"], engine="tesseract")

        assert result.engine_used == "easyocr"
        assert result.blocks[0].text == "Fallback"

    @pytest.mark.asyncio
    async def test_both_engines_missing_raises_runtime_error(self):
        """When both engines are None, RuntimeError must be raised."""
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))

        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract", None), \
             patch("nobla.tools.vision.ocr.easyocr_module", None):
            mock_gs.return_value = _make_settings(engine="tesseract")

            with pytest.raises(RuntimeError, match="No OCR engine"):
                await tool.extract(img)

    @pytest.mark.asyncio
    async def test_easyocr_to_tesseract_fallback(self):
        """When easyocr_module is None, tesseract should be used."""
        tool = OCRTool()
        img = Image.new("RGB", (100, 50))
        tess_data = {
            "text": ["FallbackTess"],
            "conf": [90],
            "left": [0],
            "top": [0],
            "width": [40],
            "height": [20],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.easyocr_module", None), \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(engine="easyocr", threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool.extract(img, languages=["en"], engine="easyocr")

        assert result.engine_used == "tesseract"
        assert result.blocks[0].text == "FallbackTess"


# ---------------------------------------------------------------------------
# execute() tests
# ---------------------------------------------------------------------------

class TestOCRToolExecute:
    @pytest.mark.asyncio
    async def test_execute_decodes_b64_and_returns_result(self):
        tool = OCRTool()
        b64 = _dummy_b64()
        tess_data = {
            "text": ["Execute"],
            "conf": [95],
            "left": [0],
            "top": [0],
            "width": [40],
            "height": [20],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool.execute(_make_params({"image_b64": b64}))

        assert result.success is True
        assert "blocks" in result.data
        assert "full_text" in result.data
        assert "engine_used" in result.data

    @pytest.mark.asyncio
    async def test_execute_returns_error_on_bad_b64(self):
        tool = OCRTool()
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs:
            mock_gs.return_value = _make_settings(threshold=0.5)
            result = await tool.execute(_make_params({"image_b64": "!!notbase64!!"}))

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_passes_languages_and_engine(self):
        """execute() should forward languages and engine from args."""
        tool = OCRTool()
        b64 = _dummy_b64()
        tess_data = {
            "text": ["Lang"],
            "conf": [95],
            "left": [0],
            "top": [0],
            "width": [40],
            "height": [20],
        }
        with patch("nobla.tools.vision.ocr.get_settings") as mock_gs, \
             patch("nobla.tools.vision.ocr.pytesseract") as mock_tess:
            mock_gs.return_value = _make_settings(threshold=0.5)
            mock_tess.image_to_data.return_value = tess_data
            mock_tess.Output = MagicMock()
            mock_tess.Output.DICT = "dict"

            result = await tool.execute(_make_params({
                "image_b64": b64,
                "languages": ["de"],
                "engine": "tesseract",
            }))

        assert result.success is True


# ---------------------------------------------------------------------------
# _decode_b64() tests
# ---------------------------------------------------------------------------

class TestDecodeB64:
    def test_decode_valid_b64_returns_pil_image(self):
        tool = OCRTool()
        b64 = _dummy_b64()
        img = tool._decode_b64(b64)
        assert isinstance(img, Image.Image)

    def test_decode_invalid_b64_raises(self):
        tool = OCRTool()
        with pytest.raises(Exception):
            tool._decode_b64("!!invalid!!")

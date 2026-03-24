"""Tests for ElementTargetingTool."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from nobla.tools.vision.detection import DetectedElement
from nobla.tools.vision.capture import CaptureResult
from nobla.tools.vision.targeting import ElementTargetingTool, TargetResult
from nobla.tools.models import ToolCategory, ToolParams
from nobla.security.permissions import Tier
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_elements() -> list[DetectedElement]:
    return [
        DetectedElement("button", "Submit", {"x": 100, "y": 200, "width": 80, "height": 30}, 0.9),
        DetectedElement("button", "Cancel", {"x": 200, "y": 200, "width": 80, "height": 30}, 0.85),
        DetectedElement("label", "Name:", {"x": 10, "y": 100, "width": 50, "height": 20}, 0.8),
        DetectedElement("heading", "Settings", {"x": 10, "y": 10, "width": 150, "height": 35}, 0.95),
        DetectedElement("link", "https://help.com", {"x": 10, "y": 300, "width": 120, "height": 20}, 0.75),
    ]


def _make_tool() -> ElementTargetingTool:
    return ElementTargetingTool()


def _dummy_capture_result() -> CaptureResult:
    img = Image.new("RGB", (800, 600), color=(200, 200, 200))
    return CaptureResult(image=img, width=800, height=600, monitor=0)


def _make_params(args: dict) -> ToolParams:
    state = MagicMock()
    return ToolParams(args=args, connection_state=state)


# ---------------------------------------------------------------------------
# 1. Metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_name(self):
        tool = _make_tool()
        assert tool.name == "ui.target_element"

    def test_category(self):
        tool = _make_tool()
        assert tool.category == ToolCategory.VISION

    def test_tier(self):
        tool = _make_tool()
        assert tool.tier == Tier.STANDARD

    def test_requires_approval(self):
        tool = _make_tool()
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# 2. Keyword extraction
# ---------------------------------------------------------------------------

class TestKeywordExtraction:
    def test_removes_stopwords(self):
        tool = _make_tool()
        result = tool._extract_keywords("the big Submit button")
        assert result == ["submit", "button"]

    def test_all_stopwords_returns_empty(self):
        tool = _make_tool()
        result = tool._extract_keywords("the a an this that")
        assert result == []

    def test_preserves_meaningful_words(self):
        tool = _make_tool()
        result = tool._extract_keywords("Save Changes")
        assert result == ["save", "changes"]


# ---------------------------------------------------------------------------
# 3. Fuzzy matching
# ---------------------------------------------------------------------------

class TestFuzzyMatching:
    def setup_method(self):
        self.tool = _make_tool()
        self.elements = _make_elements()

    def test_exact_match_high_score_correct_element(self):
        match = self.tool._best_match("Submit", self.elements)
        assert match is not None
        assert match.element.label == "Submit"
        assert match.score > 0.5

    def test_partial_match_finds_correct_element(self):
        match = self.tool._best_match("cancel button", self.elements)
        assert match is not None
        assert match.element.label == "Cancel"

    def test_type_bonus_submit_button_scores_higher_than_submit_alone(self):
        match_with_type = self.tool._best_match("Submit button", self.elements)
        match_without_type = self.tool._best_match("Submit", self.elements)
        assert match_with_type is not None
        assert match_without_type is not None
        assert match_with_type.score >= match_without_type.score

    def test_no_match_returns_none(self):
        match = self.tool._best_match("xyzqwerty nonexistent", self.elements)
        assert match is None

    def test_keyword_dilution_prevention(self):
        # "submit form" should still match "Submit" button
        match = self.tool._best_match("submit form", self.elements)
        assert match is not None
        assert match.element.label == "Submit"

    def test_fuzzy_typo_matches(self):
        # "Submitt" (typo) should match "Submit" button
        match = self.tool._best_match("Submitt", self.elements)
        assert match is not None
        assert match.element.label == "Submit"


# ---------------------------------------------------------------------------
# 4. Target composition
# ---------------------------------------------------------------------------

class TestTargetComposition:
    def setup_method(self):
        self.tool = _make_tool()
        self.elements = _make_elements()
        self.capture_result = _dummy_capture_result()

    @pytest.mark.asyncio
    async def test_returns_center_coordinates(self):
        """Submit bbox {x:100, y:200, w:80, h:30} -> center (140, 215)."""
        with (
            patch.object(type(self.tool), "_capture", new_callable=PropertyMock) as mock_cap_prop,
            patch.object(type(self.tool), "_detector", new_callable=PropertyMock) as mock_det_prop,
            patch("nobla.tools.vision.targeting.element_cache") as mock_cache,
        ):
            mock_cap = MagicMock()
            mock_cap.capture = AsyncMock(return_value=self.capture_result)
            mock_cap_prop.return_value = mock_cap

            mock_det = MagicMock()
            mock_det.detect = AsyncMock(return_value=self.elements)
            mock_det_prop.return_value = mock_det

            mock_cache.get.return_value = None  # cache miss

            result = await self.tool.target("Submit")

        assert isinstance(result, TargetResult)
        assert result.x == 140  # 100 + 80//2
        assert result.y == 215  # 200 + 30//2
        assert result.element.label == "Submit"

    @pytest.mark.asyncio
    async def test_uses_cache_when_available(self):
        """When cache has elements, detector.detect must NOT be called."""
        cached_dicts = [
            {"element_type": "button", "label": "Submit",
             "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
             "confidence": 0.9},
        ]

        with (
            patch.object(type(self.tool), "_capture", new_callable=PropertyMock) as mock_cap_prop,
            patch.object(type(self.tool), "_detector", new_callable=PropertyMock) as mock_det_prop,
            patch("nobla.tools.vision.targeting.element_cache") as mock_cache,
        ):
            mock_cap = MagicMock()
            mock_cap.capture = AsyncMock(return_value=self.capture_result)
            mock_cap_prop.return_value = mock_cap

            mock_det = MagicMock()
            mock_det.detect = AsyncMock(return_value=self.elements)
            mock_det_prop.return_value = mock_det

            mock_cache.get.return_value = cached_dicts  # cache hit

            result = await self.tool.target("Submit")

        assert result.element.label == "Submit"
        mock_det.detect.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_match_raises_value_error(self):
        """If no element matches, target() raises ValueError."""
        with (
            patch.object(type(self.tool), "_capture", new_callable=PropertyMock) as mock_cap_prop,
            patch.object(type(self.tool), "_detector", new_callable=PropertyMock) as mock_det_prop,
            patch("nobla.tools.vision.targeting.element_cache") as mock_cache,
        ):
            mock_cap = MagicMock()
            mock_cap.capture = AsyncMock(return_value=self.capture_result)
            mock_cap_prop.return_value = mock_cap

            mock_det = MagicMock()
            mock_det.detect = AsyncMock(return_value=self.elements)
            mock_det_prop.return_value = mock_det

            mock_cache.get.return_value = None

            with pytest.raises(ValueError, match="No element matching"):
                await self.tool.target("xyzqwerty nonexistent")


# ---------------------------------------------------------------------------
# 5. execute() public API
# ---------------------------------------------------------------------------

class TestExecuteApi:
    def setup_method(self):
        self.tool = _make_tool()
        self.elements = _make_elements()
        self.capture_result = _dummy_capture_result()

    @pytest.mark.asyncio
    async def test_execute_success(self):
        with (
            patch.object(type(self.tool), "_capture", new_callable=PropertyMock) as mock_cap_prop,
            patch.object(type(self.tool), "_detector", new_callable=PropertyMock) as mock_det_prop,
            patch("nobla.tools.vision.targeting.element_cache") as mock_cache,
            patch("nobla.tools.vision.targeting.get_settings") as mock_settings,
        ):
            mock_cap = MagicMock()
            mock_cap.capture = AsyncMock(return_value=self.capture_result)
            mock_cap_prop.return_value = mock_cap

            mock_det = MagicMock()
            mock_det.detect = AsyncMock(return_value=self.elements)
            mock_det_prop.return_value = mock_det

            mock_cache.get.return_value = None

            settings = MagicMock()
            settings.vision.enabled = True
            mock_settings.return_value = settings

            params = _make_params({"description": "Submit"})
            result = await self.tool.execute(params)

        assert result.success is True
        assert result.data["x"] == 140
        assert result.data["y"] == 215
        assert "element" in result.data
        assert "match_score" in result.data

    @pytest.mark.asyncio
    async def test_execute_missing_description_returns_error(self):
        with patch("nobla.tools.vision.targeting.get_settings") as mock_settings:
            settings = MagicMock()
            settings.vision.enabled = True
            mock_settings.return_value = settings

            params = _make_params({})
            result = await self.tool.execute(params)

        assert result.success is False
        assert "description" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_no_match_returns_error(self):
        with (
            patch.object(type(self.tool), "_capture", new_callable=PropertyMock) as mock_cap_prop,
            patch.object(type(self.tool), "_detector", new_callable=PropertyMock) as mock_det_prop,
            patch("nobla.tools.vision.targeting.element_cache") as mock_cache,
            patch("nobla.tools.vision.targeting.get_settings") as mock_settings,
        ):
            mock_cap = MagicMock()
            mock_cap.capture = AsyncMock(return_value=self.capture_result)
            mock_cap_prop.return_value = mock_cap

            mock_det = MagicMock()
            mock_det.detect = AsyncMock(return_value=self.elements)
            mock_det_prop.return_value = mock_det

            mock_cache.get.return_value = None

            settings = MagicMock()
            settings.vision.enabled = True
            mock_settings.return_value = settings

            params = _make_params({"description": "xyzqwerty nonexistent"})
            result = await self.tool.execute(params)

        assert result.success is False
        assert result.error is not None

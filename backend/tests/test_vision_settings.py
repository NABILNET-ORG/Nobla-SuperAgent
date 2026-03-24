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

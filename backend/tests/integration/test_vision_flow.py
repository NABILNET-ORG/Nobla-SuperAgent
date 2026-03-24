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
    async def test_safe_tier_cannot_access_vision(self, ws_client: RpcClient):
        """SAFE tier (tier=1) cannot use STANDARD vision tools."""
        # Register with SAFE tier
        await ws_client.call_expect_result(
            "system.register", {"passphrase": "safe-test", "tier": 1}
        )
        error = await ws_client.call_expect_error(
            "tool.execute",
            {"tool_name": "screenshot.capture", "args": {}},
        )
        assert error["code"] == -32042 or "permission" in error["message"].lower()

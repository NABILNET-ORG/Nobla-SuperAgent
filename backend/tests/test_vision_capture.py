"""Unit tests for ScreenshotTool (capture.py).

Tests are written before the implementation (TDD).
Mocks mss_module and get_settings to avoid real screen captures.
"""
from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.security.permissions import Tier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(args: dict) -> ToolParams:
    conn = MagicMock(spec=ConnectionState)
    return ToolParams(args=args, connection_state=conn)


def _make_settings(
    enabled: bool = True,
    fmt: str = "png",
    quality: int = 85,
    max_dim: int = 1920,
) -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.vision.enabled = enabled
    mock_settings.vision.screenshot_format = fmt
    mock_settings.vision.screenshot_quality = quality
    mock_settings.vision.screenshot_max_dimension = max_dim
    return mock_settings


def _fake_mss_ctx(width: int = 1920, height: int = 1080) -> MagicMock:
    """Build a mock mss context that returns an (width x height) blue image."""

    def _grab(rect):
        img = Image.new("RGB", (width, height), color="blue")
        result = MagicMock()
        result.rgb = img.tobytes()
        result.size = (width, height)
        return result

    ctx = MagicMock()
    ctx.monitors = [
        {"left": 0, "top": 0, "width": width, "height": height},
        {"left": 0, "top": 0, "width": width, "height": height},
    ]
    ctx.grab = MagicMock(side_effect=_grab)
    return ctx


def _patch_mss(ctx: MagicMock):
    """Return a patch for nobla.tools.vision.capture.mss_module with ctx."""
    mock_mss = MagicMock()
    mock_mss.mss.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_mss.mss.return_value.__exit__ = MagicMock(return_value=False)
    return mock_mss


# ---------------------------------------------------------------------------
# Import the tool (must succeed after implementation exists)
# ---------------------------------------------------------------------------

@pytest.fixture
def tool():
    from nobla.tools.vision.capture import ScreenshotTool
    return ScreenshotTool()


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

class TestScreenshotToolMetadata:
    def test_name(self, tool):
        assert tool.name == "screenshot.capture"

    def test_description_non_empty(self, tool):
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0

    def test_category(self, tool):
        assert tool.category == ToolCategory.VISION

    def test_tier(self, tool):
        assert tool.tier == Tier.STANDARD

    def test_requires_approval_false(self, tool):
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# describe_action tests
# ---------------------------------------------------------------------------

class TestDescribeAction:
    def test_default_monitor(self, tool):
        params = _make_params({"monitor": 0})
        desc = tool.describe_action(params)
        assert "monitor 0" in desc.lower() or "monitor" in desc.lower()

    def test_default_monitor_no_args(self, tool):
        params = _make_params({})
        desc = tool.describe_action(params)
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_with_region(self, tool):
        region = {"x": 10, "y": 20, "width": 300, "height": 200}
        params = _make_params({"monitor": 1, "region": region})
        desc = tool.describe_action(params)
        # Should mention the coordinates
        assert "10" in desc and "20" in desc
        assert "300" in desc and "200" in desc

    def test_with_region_monitor_0(self, tool):
        region = {"x": 0, "y": 0, "width": 100, "height": 100}
        params = _make_params({"region": region})
        desc = tool.describe_action(params)
        assert isinstance(desc, str)
        assert len(desc) > 0


# ---------------------------------------------------------------------------
# validate tests
# ---------------------------------------------------------------------------

class TestValidate:
    @pytest.mark.asyncio
    async def test_valid_defaults(self, tool):
        """No exception on valid default params."""
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0})
                await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_invalid_format(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                params = _make_params({"format": "bmp"})
                with pytest.raises(ValueError, match="Invalid format"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_valid_jpeg_format(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                params = _make_params({"format": "jpeg"})
                await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_valid_jpg_format(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                params = _make_params({"format": "jpg"})
                await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_valid_png_format(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                params = _make_params({"format": "png"})
                await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_vision_disabled(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings(enabled=False)
                params = _make_params({})
                with pytest.raises(ValueError, match="[Vv]ision"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_mss_not_installed(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", None):
                mock_gs.return_value = _make_settings()
                params = _make_params({})
                with pytest.raises(ValueError, match="mss"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_region_negative_x(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                region = {"x": -1, "y": 0, "width": 100, "height": 100}
                params = _make_params({"region": region})
                with pytest.raises(ValueError, match="region"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_region_negative_width(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                region = {"x": 0, "y": 0, "width": -10, "height": 100}
                params = _make_params({"region": region})
                with pytest.raises(ValueError, match="region"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_region_missing_key(self, tool):
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                region = {"x": 0, "y": 0, "width": 100}  # missing height
                params = _make_params({"region": region})
                with pytest.raises(ValueError, match="region"):
                    await tool.validate(params)

    @pytest.mark.asyncio
    async def test_region_zero_values_valid(self, tool):
        """Zero coords are acceptable (top-left origin)."""
        with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
            with patch("nobla.tools.vision.capture.mss_module", MagicMock()):
                mock_gs.return_value = _make_settings()
                region = {"x": 0, "y": 0, "width": 0, "height": 0}
                params = _make_params({"region": region})
                await tool.validate(params)  # should not raise


# ---------------------------------------------------------------------------
# capture() internal API tests
# ---------------------------------------------------------------------------

class TestCaptureMethod:
    @pytest.mark.asyncio
    async def test_returns_capture_result(self, tool):
        from nobla.tools.vision.capture import CaptureResult
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            result = await tool.capture(monitor=0)
        assert isinstance(result, CaptureResult)

    @pytest.mark.asyncio
    async def test_result_contains_pil_image(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            result = await tool.capture(monitor=0)
        assert isinstance(result.image, Image.Image)

    @pytest.mark.asyncio
    async def test_result_dimensions(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            result = await tool.capture(monitor=0)
        assert result.width == 1920
        assert result.height == 1080

    @pytest.mark.asyncio
    async def test_result_monitor_field(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            result = await tool.capture(monitor=1)
        assert result.monitor == 1

    @pytest.mark.asyncio
    async def test_capture_with_region(self, tool):
        from nobla.tools.vision.capture import CaptureResult
        ctx = _fake_mss_ctx(300, 200)
        mock_mss = _patch_mss(ctx)
        region = {"x": 10, "y": 20, "width": 300, "height": 200}
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            result = await tool.capture(monitor=0, region=region)
        assert isinstance(result, CaptureResult)
        assert isinstance(result.image, Image.Image)

    @pytest.mark.asyncio
    async def test_mss_not_installed_raises(self, tool):
        with patch("nobla.tools.vision.capture.mss_module", None):
            with pytest.raises(RuntimeError, match="mss"):
                await tool.capture(monitor=0)

    @pytest.mark.asyncio
    async def test_invalid_monitor_raises(self, tool):
        """Monitor index out of range should raise ValueError from within _grab."""
        ctx = _fake_mss_ctx()
        # Only 2 monitors (index 0 and 1); requesting index 5 should fail
        ctx.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with pytest.raises((ValueError, Exception)):
                await tool.capture(monitor=5)


# ---------------------------------------------------------------------------
# execute() public API tests
# ---------------------------------------------------------------------------

class TestExecuteMethod:
    @pytest.mark.asyncio
    async def test_success_returns_tool_result(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert isinstance(result, ToolResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_result_has_image_b64(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert "image_b64" in result.data
        # Verify it is valid base64
        decoded = base64.b64decode(result.data["image_b64"])
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_result_data_fields(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        data = result.data
        assert "width" in data
        assert "height" in data
        assert "format" in data
        assert "monitor" in data
        assert "native_width" in data
        assert "native_height" in data

    @pytest.mark.asyncio
    async def test_native_dims_preserved(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["native_width"] == 1920
        assert result.data["native_height"] == 1080

    @pytest.mark.asyncio
    async def test_format_defaults_to_settings(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(fmt="png")
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["format"] == "png"

    @pytest.mark.asyncio
    async def test_format_override_jpeg(self, tool):
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0, "format": "jpeg"})
                result = await tool.execute(params)
        assert result.data["format"] == "jpeg"

    @pytest.mark.asyncio
    async def test_base64_is_valid_png(self, tool):
        ctx = _fake_mss_ctx(100, 100)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(fmt="png")
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        raw = base64.b64decode(result.data["image_b64"])
        img = Image.open(BytesIO(raw))
        assert img.format == "PNG"

    @pytest.mark.asyncio
    async def test_base64_is_valid_jpeg(self, tool):
        ctx = _fake_mss_ctx(100, 100)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(fmt="jpeg")
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        raw = base64.b64decode(result.data["image_b64"])
        img = Image.open(BytesIO(raw))
        assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_execute_error_returns_failure(self, tool):
        """If capture raises, execute should return ToolResult(success=False)."""
        with patch("nobla.tools.vision.capture.mss_module", None):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings()
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# Downscaling tests
# ---------------------------------------------------------------------------

class TestDownscaling:
    @pytest.mark.asyncio
    async def test_4k_downscaled_to_max_dim_1920(self, tool):
        """3840x2160 with max_dimension=1920 should produce 1920x1080."""
        ctx = _fake_mss_ctx(3840, 2160)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["width"] == 1920
        assert result.data["height"] == 1080

    @pytest.mark.asyncio
    async def test_4k_native_dims_preserved(self, tool):
        """Native dimensions must always reflect the real capture size."""
        ctx = _fake_mss_ctx(3840, 2160)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["native_width"] == 3840
        assert result.data["native_height"] == 2160

    @pytest.mark.asyncio
    async def test_no_upscale_when_below_max_dim(self, tool):
        """Images smaller than max_dimension must NOT be upscaled."""
        ctx = _fake_mss_ctx(800, 600)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["width"] == 800
        assert result.data["height"] == 600

    @pytest.mark.asyncio
    async def test_aspect_ratio_preserved_landscape(self, tool):
        """Downscaling should preserve aspect ratio for landscape images."""
        ctx = _fake_mss_ctx(3840, 2160)  # 16:9
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        w, h = result.data["width"], result.data["height"]
        ratio = w / h
        assert abs(ratio - (16 / 9)) < 0.02  # within 2% tolerance

    @pytest.mark.asyncio
    async def test_aspect_ratio_preserved_portrait(self, tool):
        """Downscaling should preserve aspect ratio for portrait images."""
        ctx = _fake_mss_ctx(1080, 1920)  # portrait 9:16
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        w, h = result.data["width"], result.data["height"]
        # Portrait: height is the larger dimension; max_dim=1920 → height stays 1920
        assert result.data["height"] == 1920
        assert result.data["width"] == 1080

    @pytest.mark.asyncio
    async def test_exact_max_dim_not_scaled(self, tool):
        """Image exactly at max_dimension should not be resized."""
        ctx = _fake_mss_ctx(1920, 1080)
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=1920)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["width"] == 1920
        assert result.data["height"] == 1080

    @pytest.mark.asyncio
    async def test_custom_max_dim_500(self, tool):
        """Verify scaling math at a custom max_dimension=500."""
        ctx = _fake_mss_ctx(1000, 500)  # wider side = 1000
        mock_mss = _patch_mss(ctx)
        with patch("nobla.tools.vision.capture.mss_module", mock_mss):
            with patch("nobla.tools.vision.capture.get_settings") as mock_gs:
                mock_gs.return_value = _make_settings(max_dim=500)
                params = _make_params({"monitor": 0})
                result = await tool.execute(params)
        assert result.data["width"] == 500
        assert result.data["height"] == 250


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_tool_registered(self):
        from nobla.tools.registry import _TOOL_REGISTRY
        # Import to trigger registration
        import nobla.tools.vision.capture  # noqa: F401
        assert "screenshot.capture" in _TOOL_REGISTRY

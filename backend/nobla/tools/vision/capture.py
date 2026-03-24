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

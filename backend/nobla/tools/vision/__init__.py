"""Vision tools — auto-discovery imports."""

# Import modules to trigger @register_tool decorators.
# Import order does not matter — tools resolve siblings lazily via
# ToolRegistry.get() properties, not at import time.
from nobla.tools.vision import capture  # noqa: F401
from nobla.tools.vision import ocr  # noqa: F401
from nobla.tools.vision import detection  # noqa: F401
from nobla.tools.vision import targeting  # noqa: F401

# The shared element_cache singleton lives in cache.py (not here)
# to avoid circular imports. Tools import it directly:
#   from nobla.tools.vision.cache import element_cache

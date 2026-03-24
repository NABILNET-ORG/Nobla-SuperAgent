"""Code execution tools — auto-discovery and shared helpers."""
from __future__ import annotations

PACKAGEABLE_LANGUAGES = {"python", "javascript"}

PACKAGE_MOUNT = "/packages"

PACKAGE_ENV: dict[str, dict[str, str]] = {
    "python": {"PYTHONPATH": "/packages/python"},
    "javascript": {"NODE_PATH": "/packages/node/node_modules"},
}


def get_volume_name(prefix: str, language: str, connection_id: str) -> str:
    """Build a Docker volume name. Shared by runner and packages tools."""
    return f"{prefix}-{language}-{connection_id[:8]}"


# Auto-discovery: importing submodules triggers @register_tool decorators.
from nobla.tools.code import runner  # noqa: E402, F401
# Remaining imports added as tools are implemented in Tasks 3-6:
from nobla.tools.code import packages  # noqa: E402, F401
from nobla.tools.code import codegen  # noqa: E402, F401
# from nobla.tools.code import debug  # noqa: E402, F401
# from nobla.tools.code import git  # noqa: E402, F401

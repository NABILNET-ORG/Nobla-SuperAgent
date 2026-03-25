"""Phase 4D: Remote Control tools.

Auto-discovery imports trigger @register_tool decorators.
Kill switch callbacks close SSH sessions on emergency stop.
"""

from nobla.tools.remote import ssh_connect  # noqa: F401
from nobla.tools.remote import ssh_exec  # noqa: F401
from nobla.tools.remote import sftp_manage  # noqa: F401

# ---- kill switch integration ----

def _register_kill_switch() -> None:
    """Register remote control callbacks with the kill switch."""
    try:
        from nobla.security.killswitch import kill_switch
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.safety import RemoteControlGuard

        kill_switch.on_soft_kill(RemoteControlGuard.halt)

        async def _halt_pool():
            await _get_pool().halt()

        kill_switch.on_hard_kill(_halt_pool)
    except Exception:
        pass  # Kill switch may not be initialised yet

_register_kill_switch()

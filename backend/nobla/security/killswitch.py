from __future__ import annotations
import asyncio
import enum
import structlog

logger = structlog.get_logger()


class KillState(enum.Enum):
    RUNNING = "running"
    SOFT_KILLING = "soft_killing"
    KILLED = "killed"


class KillSwitch:
    def __init__(self, grace_period: float = 5.0):
        self.state = KillState.RUNNING
        self.grace_period = grace_period
        self._hard_kill_task: asyncio.Task | None = None
        self._on_soft_kill_callbacks: list[callable] = []
        self._on_hard_kill_callbacks: list[callable] = []

    @property
    def is_accepting_requests(self) -> bool:
        return self.state == KillState.RUNNING

    def on_soft_kill(self, callback: callable) -> None:
        self._on_soft_kill_callbacks.append(callback)

    def on_hard_kill(self, callback: callable) -> None:
        self._on_hard_kill_callbacks.append(callback)

    async def soft_kill(self) -> None:
        if self.state == KillState.SOFT_KILLING:
            await self.hard_kill()
            return
        if self.state == KillState.KILLED:
            return

        logger.warning("kill_switch_soft", state="soft_killing")
        self.state = KillState.SOFT_KILLING

        for cb in self._on_soft_kill_callbacks:
            try:
                await cb() if asyncio.iscoroutinefunction(cb) else cb()
            except Exception as e:
                logger.error("soft_kill_callback_error", error=str(e))

        self._hard_kill_task = asyncio.create_task(self._delayed_hard_kill())

    async def hard_kill(self) -> None:
        if self._hard_kill_task and not self._hard_kill_task.done():
            self._hard_kill_task.cancel()

        logger.warning("kill_switch_hard", state="killed")
        self.state = KillState.KILLED

        for cb in self._on_hard_kill_callbacks:
            try:
                await cb() if asyncio.iscoroutinefunction(cb) else cb()
            except Exception as e:
                logger.error("hard_kill_callback_error", error=str(e))

    async def resume(self) -> None:
        logger.info("kill_switch_resume", state="running")
        self.state = KillState.RUNNING

    async def _delayed_hard_kill(self) -> None:
        try:
            await asyncio.sleep(self.grace_period)
            if self.state == KillState.SOFT_KILLING:
                await self.hard_kill()
        except asyncio.CancelledError:
            pass

from __future__ import annotations
from dataclasses import dataclass
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

LANGUAGE_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
    "bash": "bash:5",
}


class SandboxConfig(BaseModel):
    runtime: str = "docker"
    memory_limit: str = "256m"
    cpu_limit: float = 1.0
    timeout_seconds: int = 30
    network_enabled: bool = False
    allowed_images: list[str] = ["python:3.12-slim", "node:20-slim", "bash:5"]


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    timed_out: bool


class SandboxManager:
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._client = None

    def get_image(self, language: str) -> str | None:
        image = LANGUAGE_IMAGES.get(language)
        if image and image in self.config.allowed_images:
            return image
        return None

    async def execute(self, code: str, language: str = "python", timeout: int | None = None) -> SandboxResult:
        """Execute code in a Docker container. Requires Docker daemon running."""
        import time
        image = self.get_image(language)
        if not image:
            return SandboxResult(stdout="", stderr=f"Unsupported language: {language}", exit_code=1, execution_time_ms=0, timed_out=False)

        timeout = timeout or self.config.timeout_seconds

        try:
            import docker
            if not self._client:
                self._client = docker.from_env()

            start = time.monotonic()
            container = self._client.containers.run(
                image=image,
                command=self._build_command(code, language),
                detach=True,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                network_mode="none" if not self.config.network_enabled else "bridge",
                runtime="runsc" if self.config.runtime == "gvisor" else None,
                read_only=True,
                tmpfs={"/tmp": "size=64m"},
            )

            try:
                result = container.wait(timeout=timeout)
                elapsed = int((time.monotonic() - start) * 1000)
                stdout = container.logs(stdout=True, stderr=False).decode()
                stderr = container.logs(stdout=False, stderr=True).decode()
                return SandboxResult(
                    stdout=stdout, stderr=stderr,
                    exit_code=result.get("StatusCode", -1),
                    execution_time_ms=elapsed, timed_out=False,
                )
            except Exception:
                elapsed = int((time.monotonic() - start) * 1000)
                container.kill()
                return SandboxResult(stdout="", stderr="Execution timed out", exit_code=-1, execution_time_ms=elapsed, timed_out=True)
            finally:
                container.remove(force=True)

        except ImportError:
            return SandboxResult(stdout="", stderr="Docker SDK not available", exit_code=1, execution_time_ms=0, timed_out=False)
        except Exception as e:
            logger.error("sandbox_error", error=str(e))
            return SandboxResult(stdout="", stderr=str(e), exit_code=1, execution_time_ms=0, timed_out=False)

    def _build_command(self, code: str, language: str) -> list[str]:
        if language == "python":
            return ["python", "-c", code]
        elif language == "javascript":
            return ["node", "-e", code]
        elif language == "bash":
            return ["bash", "-c", code]
        return ["echo", "unsupported"]

    async def kill_all(self) -> None:
        """Kill all running sandbox containers. Used by kill switch."""
        try:
            import docker
            if not self._client:
                self._client = docker.from_env()
            containers = self._client.containers.list(filters={"ancestor": list(LANGUAGE_IMAGES.values())})
            for c in containers:
                try:
                    c.kill()
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error("kill_all_error", error=str(e))

    async def cleanup(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

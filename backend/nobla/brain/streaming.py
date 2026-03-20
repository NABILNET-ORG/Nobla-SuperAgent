"""WebSocket streaming coordinator for LLM token-by-token responses."""

from __future__ import annotations
import asyncio
from enum import Enum
from typing import AsyncIterator
from fastapi import WebSocket
import structlog

logger = structlog.get_logger(__name__)


class StreamState(str, Enum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class StreamSession:
    """Manages a single streaming response session."""

    def __init__(self, ws: WebSocket, conversation_id: str, model: str, buffer_size: int = 100) -> None:
        self._ws = ws
        self._conversation_id = conversation_id
        self._model = model
        self._buffer_size = buffer_size
        self._cancelled = asyncio.Event()
        self._state = StreamState.PENDING
        self._full_text = ""
        self._token_count = 0

    @property
    def state(self) -> StreamState:
        return self._state

    @property
    def full_text(self) -> str:
        return self._full_text

    @property
    def token_count(self) -> int:
        return self._token_count

    def cancel(self) -> None:
        self._cancelled.set()
        self._state = StreamState.CANCELLED

    async def _send_notification(self, method: str, params: dict) -> None:
        await self._ws.send_json({"jsonrpc": "2.0", "method": method, "params": params})

    async def run(self, token_stream: AsyncIterator[str]) -> None:
        if self._cancelled.is_set():
            return

        self._state = StreamState.STREAMING
        await self._send_notification("chat.stream.start", {
            "conversation_id": self._conversation_id, "model": self._model,
        })

        try:
            index = 0
            async for token in token_stream:
                if self._cancelled.is_set():
                    self._state = StreamState.CANCELLED
                    break
                self._full_text += token
                self._token_count += 1
                await self._send_notification("chat.stream.token", {"content": token, "index": index})
                index += 1

            if self._state == StreamState.STREAMING:
                self._state = StreamState.COMPLETED

        except Exception as exc:
            self._state = StreamState.ERROR
            logger.error("stream.error", conversation_id=self._conversation_id, error=str(exc))
            await self._send_notification("chat.stream.error", {"code": -32000, "message": str(exc)})
            return

        if self._state == StreamState.COMPLETED:
            await self._send_notification("chat.stream.end", {
                "tokens_output": self._token_count,
                "model": self._model,
                "conversation_id": self._conversation_id,
            })

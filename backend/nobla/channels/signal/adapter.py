"""Signal channel adapter via signal-cli JSON-RPC daemon (Phase 5-Channels).

Implements ``BaseChannelAdapter`` to connect Signal via signal-cli's
JSON-RPC interface over TCP. signal-cli must already be registered and
running as a daemon (``signal-cli -a +NUMBER daemon --json-rpc``).

Transport: asyncio TCP connection to signal-cli JSON-RPC 2.0 daemon.
No HTTP, no webhook -- pure TCP with newline-delimited JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.signal.formatter import format_response
from nobla.channels.signal.handlers import SignalHandlers
from nobla.channels.signal.media import save_attachment_to_disk
from nobla.channels.signal.models import RPC_METHODS

logger = logging.getLogger(__name__)

# Maximum reconnection backoff in seconds
MAX_RECONNECT_DELAY = 30


class SignalRPCError(Exception):
    """Error returned by the signal-cli JSON-RPC daemon."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(message)


class SignalAdapter(BaseChannelAdapter):
    """Signal adapter using signal-cli JSON-RPC daemon over TCP.

    Args:
        settings: Signal configuration (phone, host, port, etc.).
        handlers: Pre-built ``SignalHandlers`` with linking + event bus.
    """

    def __init__(self, settings: Any, handlers: SignalHandlers) -> None:
        self._settings = settings
        self._handlers = handlers
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._receive_task: asyncio.Task | None = None
        self._running = False
        self._rpc_id = 0
        self._rpc_lock = asyncio.Lock()
        self._pending_responses: dict[int, asyncio.Future[dict[str, Any]]] = {}

    @property
    def name(self) -> str:
        return "signal"

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Connect to the signal-cli JSON-RPC daemon and start receiving."""
        if self._running:
            logger.warning("Signal adapter already running")
            return

        host = self._settings.rpc_host
        port = self._settings.rpc_port

        self._reader, self._writer = await asyncio.open_connection(
            host, port
        )

        # Wire handler functions
        self._handlers.set_send_fn(self._send_raw_text)
        self._handlers.set_send_receipt_fn(self.send_read_receipt)
        self._handlers.set_data_dir(self._settings.data_dir)

        self._running = True
        await self._start_receive_loop()
        logger.info(
            "Signal adapter started (host=%s, port=%d)", host, port
        )

    async def stop(self) -> None:
        """Gracefully shut down the TCP connection."""
        if not self._running and not self._writer:
            return

        self._running = False

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receive_task = None

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        logger.info("Signal adapter stopped")

    # ── Outbound messaging ────────────────────────────────

    async def send(
        self,
        channel_user_id: str,
        response: ChannelResponse,
        is_group: bool = False,
    ) -> None:
        """Send a formatted response to a Signal user or group."""
        # Send attachments first
        for attachment in response.attachments:
            if attachment.data and self._settings.data_dir:
                file_path = save_attachment_to_disk(
                    attachment, self._settings.data_dir
                )
                params: dict[str, Any] = {
                    "attachment": [file_path],
                }
                if is_group:
                    params["groupId"] = channel_user_id
                else:
                    params["recipient"] = [channel_user_id]
                await self._rpc_call("send", **params)

        # Format and send text messages
        if response.content or response.actions:
            formatted = format_response(response)
            for msg in formatted:
                if is_group:
                    await self._rpc_call(
                        "send",
                        groupId=channel_user_id,
                        message=msg.text,
                    )
                else:
                    await self._rpc_call(
                        "send",
                        recipient=[channel_user_id],
                        message=msg.text,
                    )

    async def send_notification(
        self, channel_user_id: str, text: str
    ) -> None:
        """Send a plain-text notification."""
        await self._send_raw_text(channel_user_id, text)

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Signal has no interactive callbacks -- always returns no-op."""
        return "", {}

    async def send_read_receipt(
        self, source: str, timestamp: int
    ) -> None:
        """Send a read receipt to acknowledge a received message."""
        await self._rpc_call(
            "sendReceipt",
            recipient=source,
            timestamp=timestamp,
            type="read",
        )

    async def health_check(self) -> bool:
        """Check connectivity by calling the version RPC method."""
        try:
            result = await self._rpc_call("version")
            return isinstance(result, dict) and "version" in result
        except Exception:
            logger.exception("Signal health check failed")
            return False

    # ── JSON-RPC 2.0 transport ────────────────────────────

    async def _rpc_call(
        self, method: str, **params: Any
    ) -> dict[str, Any]:
        """Make a JSON-RPC 2.0 call to signal-cli and return the result.

        Uses a Future-based response routing mechanism so that the
        receive loop (which owns the StreamReader) resolves RPC
        responses without a read race.

        Args:
            method: RPC method name (will be looked up in RPC_METHODS).
            **params: Method parameters.

        Returns:
            The 'result' field from the JSON-RPC response.

        Raises:
            SignalRPCError: If the response contains an error.
            ConnectionError: If not connected.
            asyncio.TimeoutError: If no response within 10 seconds.
        """
        if not self._writer:
            raise ConnectionError("Not connected to signal-cli daemon")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        async with self._rpc_lock:
            self._rpc_id += 1
            request_id = self._rpc_id

            # Register the pending response before writing
            self._pending_responses[request_id] = future

            # Look up the canonical method name
            rpc_method = RPC_METHODS.get(method, method)

            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": rpc_method,
            }
            if params:
                request["params"] = params

            data = json.dumps(request) + "\n"
            self._writer.write(data.encode())
            await self._writer.drain()

        # Wait for the receive loop to resolve our future
        try:
            response = await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            self._pending_responses.pop(request_id, None)
            raise asyncio.TimeoutError(
                f"signal-cli RPC call '{method}' timed out after 10s"
            )

        if "error" in response:
            err = response["error"]
            raise SignalRPCError(
                code=err.get("code", -1),
                message=err.get("message", "Unknown RPC error"),
            )

        return response.get("result", {})

    # ── Receive loop ──────────────────────────────────────

    async def _start_receive_loop(self) -> None:
        """Start the background task that reads inbound envelopes."""
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Continuously read JSON-RPC messages from signal-cli.

        Routes RPC responses (messages with an ``id`` field) to the
        corresponding pending Future.  Notifications (no ``id``) are
        dispatched to handlers.

        Reconnects with exponential backoff on connection failures.
        """
        attempt = 0

        while self._running:
            try:
                if not self._reader:
                    break

                line = await self._reader.readline()
                if not line:
                    # Connection closed -- fail all pending RPCs
                    self._fail_pending(
                        ConnectionError("Connection closed by signal-cli")
                    )
                    if self._running:
                        await self._reconnect(attempt)
                        attempt += 1
                    continue

                attempt = 0  # Reset on successful read
                data = json.loads(line.decode().strip())

                # RPC response -- has an 'id' field
                resp_id = data.get("id")
                if resp_id is not None:
                    future = self._pending_responses.pop(resp_id, None)
                    if future and not future.done():
                        future.set_result(data)
                    continue

                # JSON-RPC notification -- no 'id' field
                if "method" in data:
                    params = data.get("params", {})
                    if "envelope" in params:
                        await self._handlers.handle_message(
                            params["envelope"]
                        )

            except asyncio.CancelledError:
                self._fail_pending(
                    asyncio.CancelledError("Receive loop cancelled")
                )
                break
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from signal-cli")
            except ConnectionError:
                self._fail_pending(ConnectionError("Connection lost"))
                if self._running:
                    await self._reconnect(attempt)
                    attempt += 1
            except Exception:
                logger.exception("Error in Signal receive loop")
                if self._running:
                    await self._reconnect(attempt)
                    attempt += 1

    async def _reconnect(self, attempt: int) -> None:
        """Reconnect to signal-cli with exponential backoff."""
        delay = self._reconnect_delay(attempt)
        logger.warning(
            "Signal connection lost. Reconnecting in %ds (attempt %d)...",
            delay,
            attempt + 1,
        )
        await asyncio.sleep(delay)

        try:
            host = self._settings.rpc_host
            port = self._settings.rpc_port
            self._reader, self._writer = await asyncio.open_connection(
                host, port
            )
            logger.info("Signal reconnected to %s:%d", host, port)
        except Exception:
            logger.exception("Signal reconnection failed")

    @staticmethod
    def _reconnect_delay(attempt: int) -> int:
        """Calculate reconnection delay with exponential backoff.

        Returns min(2^attempt, 30) but at least 1 second.
        """
        return min(2**attempt, MAX_RECONNECT_DELAY) if attempt > 0 else 1

    # ── Private helpers ───────────────────────────────────

    def _fail_pending(self, exc: BaseException) -> None:
        """Resolve all pending RPC futures with an exception."""
        for rid, future in list(self._pending_responses.items()):
            if not future.done():
                future.set_exception(exc)
        self._pending_responses.clear()

    async def _send_raw_text(
        self, recipient: str, text: str
    ) -> None:
        """Send a plain text message via JSON-RPC."""
        try:
            await self._rpc_call(
                "send",
                recipient=[recipient],
                message=text,
            )
        except Exception:
            logger.exception("Failed to send text to %s", recipient)

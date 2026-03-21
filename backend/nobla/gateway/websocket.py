"""
WebSocket handler with JSON-RPC 2.0 dispatch.
Manages WebSocket connections, routes incoming JSON-RPC messages to
registered method handlers, and sends back responses. Integrates
auth, permissions, kill switch, audit, and cost checks (Phase 1B).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from nobla.brain.base_provider import LLMMessage
from nobla.brain.router import LLMRouter
from nobla.brain.streaming import StreamSession
from nobla.gateway.protocol import (
    JsonRpcError,
    JsonRpcRequest,
    parse_message,
    create_error_response,
    create_success_response,
    METHOD_NOT_FOUND,
    INTERNAL_ERROR,
    PARSE_ERROR,
)
from nobla.security.permissions import Tier, InsufficientPermissions
from nobla.security.costs import BudgetExceeded

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Error Codes (Phase 1B)
# ---------------------------------------------------------------------------

AUTH_REQUIRED = -32011
AUTH_FAILED = -32012
TOKEN_EXPIRED = -32013
PERMISSION_DENIED = -32010
BUDGET_EXCEEDED = -32020
SERVER_KILLED = -32030

# Methods that do not require authentication
NO_AUTH_METHODS = {"system.health", "system.authenticate", "system.register"}

# Methods allowed even when server is killed
KILL_EXEMPT_METHODS = {"system.health", "system.resume"}


# ---------------------------------------------------------------------------
# Connection State
# ---------------------------------------------------------------------------


@dataclass
class ConnectionState:
    """Tracks per-connection metadata."""

    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    tier: int = 1  # Default: SAFE
    passphrase_hash: str | None = None  # Cached for escalation checks


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Tracks active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, tuple[WebSocket, ConnectionState]] = {}

    async def connect(self, ws: WebSocket) -> ConnectionState:
        """Accept a WebSocket connection and register it."""
        await ws.accept()
        state = ConnectionState()
        self._connections[state.connection_id] = (ws, state)
        logger.info("ws.connected", connection_id=state.connection_id)
        return state

    def disconnect(self, connection_id: str) -> None:
        """Remove a connection from the active set."""
        self._connections.pop(connection_id, None)
        logger.info("ws.disconnected", connection_id=connection_id)

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict) -> None:
        """Send a message to all connected clients."""
        for ws, _ in self._connections.values():
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Method Registry
# ---------------------------------------------------------------------------

# Handler signature: (params: dict, state: ConnectionState) -> Any
_HandlerFn = Callable[[dict, ConnectionState], Awaitable[Any]]
_method_registry: dict[str, _HandlerFn] = {}


def rpc_method(name: str):
    """Decorator to register an async function as a JSON-RPC method handler."""

    def decorator(fn: _HandlerFn) -> _HandlerFn:
        _method_registry[name] = fn
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Service accessors (set during app lifespan)
# ---------------------------------------------------------------------------

_llm_router: LLMRouter | None = None
_auth_service = None
_kill_switch = None
_cost_tracker = None
_permission_checker = None
_sandbox_manager = None


def set_router(router: LLMRouter) -> None:
    global _llm_router
    _llm_router = router


def get_router() -> LLMRouter | None:
    return _llm_router


def set_auth_service(svc) -> None:
    global _auth_service
    _auth_service = svc


def get_auth_service():
    return _auth_service


def set_kill_switch(ks) -> None:
    global _kill_switch
    _kill_switch = ks


def get_kill_switch():
    return _kill_switch


def set_cost_tracker(ct) -> None:
    global _cost_tracker
    _cost_tracker = ct


def get_cost_tracker():
    return _cost_tracker


def set_permission_checker(pc) -> None:
    global _permission_checker
    _permission_checker = pc


def get_permission_checker():
    return _permission_checker


def set_sandbox_manager(sm) -> None:
    global _sandbox_manager
    _sandbox_manager = sm


def get_sandbox_manager():
    return _sandbox_manager


_memory_orchestrator = None


def set_memory_orchestrator(orch) -> None:
    global _memory_orchestrator
    _memory_orchestrator = orch


def get_memory_orchestrator():
    return _memory_orchestrator


# ---------------------------------------------------------------------------
# Built-in RPC Handlers
# ---------------------------------------------------------------------------


@rpc_method("system.health")
async def handle_system_health(params: dict, state: ConnectionState) -> dict:
    ks = get_kill_switch()
    return {
        "status": "ok",
        "kill_state": ks.state.value if ks else "unknown",
    }


@rpc_method("system.status")
async def handle_system_status(params: dict, state: ConnectionState) -> dict:
    return {
        "version": "0.1.0",
        "phase": "1D",
        "providers": [],
    }


@rpc_method("system.register")
async def handle_system_register(params: dict, state: ConnectionState) -> dict:
    auth = get_auth_service()
    if not auth:
        raise RuntimeError("Auth service not initialized")

    passphrase = params.get("passphrase", "")
    display_name = params.get("display_name", "User")

    if not auth.validate_passphrase(passphrase):
        return {"error": "Passphrase too short", "min_length": auth.min_passphrase_length}

    user_id = str(uuid.uuid4())
    hashed = auth.hash_passphrase(passphrase)

    access_token = auth.create_access_token(user_id=user_id)
    refresh_token = auth.create_refresh_token(user_id=user_id)

    state.user_id = user_id
    state.passphrase_hash = hashed
    state.tier = 1

    return {
        "user_id": user_id,
        "display_name": display_name,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@rpc_method("system.authenticate")
async def handle_system_authenticate(params: dict, state: ConnectionState) -> dict:
    auth = get_auth_service()
    if not auth:
        return {"authenticated": False, "message": "Auth service not initialized"}

    passphrase = params.get("passphrase", "")
    token = params.get("token", "")

    # Token-based auth
    if token:
        payload = auth.decode_token(token)
        if payload and payload.get("type") == "access":
            state.user_id = payload["sub"]
            state.tier = 1
            return {
                "authenticated": True,
                "user_id": state.user_id,
                "tier": state.tier,
            }
        return {"authenticated": False, "message": "Invalid or expired token"}

    # Passphrase-based auth
    if not passphrase:
        return {"authenticated": False, "message": "Passphrase or token required"}

    # Phase 1B: single-user — check against the connection's cached hash
    if state.passphrase_hash and auth.verify_passphrase(passphrase, state.passphrase_hash):
        access_token = auth.create_access_token(user_id=state.user_id or "default")
        refresh_token = auth.create_refresh_token(user_id=state.user_id or "default")
        state.tier = 1
        return {
            "authenticated": True,
            "user_id": state.user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "tier": state.tier,
        }

    return {"authenticated": False, "message": "Invalid passphrase"}


@rpc_method("system.refresh")
async def handle_system_refresh(params: dict, state: ConnectionState) -> dict:
    auth = get_auth_service()
    if not auth:
        raise RuntimeError("Auth service not initialized")

    refresh_token = params.get("refresh_token", "")
    payload = auth.decode_token(refresh_token)

    if not payload or payload.get("type") != "refresh":
        return {"error": "Invalid refresh token"}

    user_id = payload["sub"]
    new_access = auth.create_access_token(user_id=user_id)
    new_refresh = auth.create_refresh_token(user_id=user_id)

    state.user_id = user_id

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
    }


@rpc_method("system.escalate")
async def handle_system_escalate(params: dict, state: ConnectionState) -> dict:
    auth = get_auth_service()
    pc = get_permission_checker()
    target_tier = params.get("tier", 1)

    # De-escalation always allowed
    if target_tier <= state.tier:
        state.tier = target_tier
        return {"tier": state.tier}

    # Check if passphrase required for escalation
    if pc and pc.requires_passphrase_for_escalation(target_tier):
        passphrase = params.get("passphrase", "")
        if not passphrase:
            return {"error": "Passphrase required for escalation to this tier"}
        if state.passphrase_hash and auth and not auth.verify_passphrase(passphrase, state.passphrase_hash):
            return {"error": "Invalid passphrase"}

    state.tier = target_tier
    return {"tier": state.tier}


@rpc_method("system.kill")
async def handle_system_kill(params: dict, state: ConnectionState) -> dict:
    ks = get_kill_switch()
    if not ks:
        return {"error": "Kill switch not initialized"}

    await ks.soft_kill()
    return {"state": ks.state.value}


@rpc_method("system.resume")
async def handle_system_resume(params: dict, state: ConnectionState) -> dict:
    ks = get_kill_switch()
    if not ks:
        return {"error": "Kill switch not initialized"}

    await ks.resume()
    return {"state": ks.state.value}


@rpc_method("system.costs")
async def handle_system_costs(params: dict, state: ConnectionState) -> dict:
    ct = get_cost_tracker()
    if not ct:
        return {"error": "Cost tracker not initialized"}
    return ct.get_dashboard()


@rpc_method("code.execute")
async def handle_code_execute(params: dict, state: ConnectionState) -> dict:
    # Requires STANDARD tier
    pc = get_permission_checker()
    if pc:
        pc.check(current_tier=Tier(state.tier), required_tier=Tier.STANDARD)

    sm = get_sandbox_manager()
    if not sm:
        return {"error": "Sandbox not initialized"}

    code = params.get("code", "")
    language = params.get("language", "python")
    timeout = params.get("timeout")

    result = await sm.execute(code=code, language=language, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
        "timed_out": result.timed_out,
    }


@rpc_method("chat.send")
async def handle_chat_send(params: dict, state: ConnectionState) -> dict:
    message = params.get("message", "")
    conversation_id = params.get("conversation_id", str(uuid.uuid4()))
    conv_uuid = uuid.UUID(conversation_id)

    # 1. Hot path: store user message + extract
    memory = get_memory_orchestrator()
    if memory:
        await memory.process_message(
            conversation_id=conv_uuid,
            role="user",
            content=message,
        )

    # 2. Retrieve memory context
    memory_context = ""
    if memory and state.user_id:
        memory_context = await memory.get_memory_context(
            user_id=uuid.UUID(state.user_id),
            query=message,
        )

    # 3. Build messages for LLM
    router = get_router()
    if not router:
        raise RuntimeError("LLM router not initialized")

    llm_messages = []
    if memory_context:
        llm_messages.append(LLMMessage(role="system", content=f"[Memory] {memory_context}"))
    llm_messages.append(LLMMessage(role="user", content=message))

    # 4. Route to LLM (persona-aware)
    from nobla.persona.service import resolve_and_route, get_persona_manager
    if get_persona_manager() is not None:
        response, _persona_ctx = await resolve_and_route(
            messages=llm_messages,
            session_id=state.connection_id,
            user_id=state.user_id or "",
            router=router,
        )
    else:
        response = await router.route(llm_messages)

    # 5. Hot path: store assistant response
    if memory:
        await memory.process_message(
            conversation_id=conv_uuid,
            role="assistant",
            content=response.content,
            model_used=response.model,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            cost_usd=response.cost_usd,
        )

    # IMPORTANT: Preserve existing response field names for Flutter compatibility
    return {
        "message": response.content,
        "model": response.model,
        "tokens_used": response.total_tokens,
        "cost_usd": response.cost_usd,
        "conversation_id": conversation_id,
    }


# ---------------------------------------------------------------------------
# Streaming Chat (Phase 2B)
# ---------------------------------------------------------------------------

_active_streams: dict[str, StreamSession] = {}


@rpc_method("chat.stream")
async def handle_chat_stream(params: dict, state: ConnectionState) -> dict:
    """Start a streaming LLM response. Tokens arrive as notifications."""
    message = params.get("message", "")
    conversation_id = params.get("conversation_id", str(uuid.uuid4()))

    router = get_router()
    if not router:
        raise RuntimeError("LLM router not initialized")

    memory = get_memory_orchestrator()
    if memory:
        conv_uuid = uuid.UUID(conversation_id)
        await memory.process_message(conversation_id=conv_uuid, role="user", content=message)

    memory_context = ""
    if memory and state.user_id:
        memory_context = await memory.get_memory_context(user_id=uuid.UUID(state.user_id), query=message)

    llm_messages = []
    if memory_context:
        llm_messages.append(LLMMessage(role="system", content=f"[Memory] {memory_context}"))
    llm_messages.append(LLMMessage(role="user", content=message))

    provider_name, token_iter = await router.stream_route(llm_messages)

    ws_pair = manager._connections.get(state.connection_id)
    if not ws_pair:
        raise RuntimeError("WebSocket connection not found")
    ws, _ = ws_pair

    session = StreamSession(ws=ws, conversation_id=conversation_id, model=provider_name)
    _active_streams[conversation_id] = session

    async def run_stream():
        try:
            await session.run(token_iter)
        finally:
            _active_streams.pop(conversation_id, None)
            if memory and session.full_text:
                await memory.process_message(
                    conversation_id=uuid.UUID(conversation_id),
                    role="assistant", content=session.full_text, model_used=provider_name,
                )

    asyncio.create_task(run_stream())
    return {"conversation_id": conversation_id, "model": provider_name, "streaming": True}


@rpc_method("chat.stream.cancel")
async def handle_chat_stream_cancel(params: dict, state: ConnectionState) -> dict:
    conversation_id = params.get("conversation_id", "")
    session = _active_streams.get(conversation_id)
    if session:
        session.cancel()
        return {"cancelled": True, "partial_text": session.full_text}
    return {"cancelled": False, "error": "No active stream for this conversation"}


# ---------------------------------------------------------------------------
# Conversation RPC Handlers (Phase 2A)
# ---------------------------------------------------------------------------


@rpc_method("conversation.list")
async def handle_conversation_list(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    conversations = await memory.list_conversations(
        user_id=uuid.UUID(state.user_id),
        limit=params.get("limit", 20),
        offset=params.get("offset", 0),
    )
    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "summary": c.summary,
                "topics": c.topics or [],
                "message_count": c.message_count,
                "updated_at": c.updated_at,
                "created_at": c.created_at,
            }
            for c in conversations
        ]
    }


@rpc_method("conversation.get")
async def handle_conversation_get(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    conv_id = uuid.UUID(params["conversation_id"])
    messages = await memory.get_messages(conv_id, limit=params.get("limit", 50))
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "model_used": m.model_used,
            }
            for m in messages
        ]
    }


@rpc_method("conversation.create")
async def handle_conversation_create(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    conv = await memory.create_conversation(
        user_id=uuid.UUID(state.user_id),
        title=params.get("title"),
    )
    return {"conversation_id": str(conv.id), "title": conv.title}


@rpc_method("conversation.archive")
async def handle_conversation_archive(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    success = await memory.archive_conversation(uuid.UUID(params["conversation_id"]))
    return {"archived": success}


@rpc_method("conversation.rename")
async def handle_conversation_rename(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    success = await memory.rename_conversation(
        uuid.UUID(params["conversation_id"]),
        params["title"],
    )
    return {"renamed": success}


@rpc_method("conversation.search")
async def handle_conversation_search(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    results = await memory.search_conversations(
        user_id=uuid.UUID(state.user_id),
        query=params["query"],
        limit=params.get("limit", 10),
    )
    return {"results": results}


@rpc_method("conversation.pause")
async def handle_conversation_pause(params: dict, state: ConnectionState) -> dict:
    """Flutter sends this on AppLifecycleState.paused. Releases working memory."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")
    conv_id = uuid.UUID(params["conversation_id"])
    memory.release_working_memory(conv_id)
    return {"status": "paused"}


# ---------------------------------------------------------------------------
# Message Handling
# ---------------------------------------------------------------------------


async def handle_message(
    ws: WebSocket, raw: str, state: ConnectionState
) -> None:
    """Parse a raw JSON-RPC message, dispatch to the handler, send response."""
    parsed = parse_message(raw)

    # Parse error -- send error response immediately
    if isinstance(parsed, JsonRpcError):
        await ws.send_json(parsed.to_dict())
        return

    request: JsonRpcRequest = parsed

    # --- Kill switch check ---
    ks = get_kill_switch()
    if ks and not ks.is_accepting_requests and request.method not in KILL_EXEMPT_METHODS:
        resp = create_error_response(
            code=SERVER_KILLED,
            message="Server is shutting down",
            data={"state": ks.state.value},
            request_id=request.id,
        )
        await ws.send_json(resp)
        return

    # --- Auth check ---
    if request.method not in NO_AUTH_METHODS and state.user_id is None:
        resp = create_error_response(
            code=AUTH_REQUIRED,
            message="Authentication required",
            data={"method": request.method},
            request_id=request.id,
        )
        await ws.send_json(resp)
        return

    # Look up method handler
    handler = _method_registry.get(request.method)
    if handler is None:
        resp = create_error_response(
            code=METHOD_NOT_FOUND,
            message="Method not found",
            data={"method": request.method},
            request_id=request.id,
        )
        await ws.send_json(resp)
        return

    # Execute handler
    try:
        result = await handler(request.params, state)
        resp = create_success_response(result=result, request_id=request.id)
        await ws.send_json(resp)
    except InsufficientPermissions as exc:
        resp = create_error_response(
            code=PERMISSION_DENIED,
            message=str(exc),
            data={"required_tier": exc.required_tier.value, "current_tier": exc.current_tier.value},
            request_id=request.id,
        )
        await ws.send_json(resp)
    except BudgetExceeded as exc:
        resp = create_error_response(
            code=BUDGET_EXCEEDED,
            message=str(exc),
            data={"period": exc.period, "limit": exc.limit, "spent": exc.spent},
            request_id=request.id,
        )
        await ws.send_json(resp)
    except Exception as exc:
        logger.error(
            "rpc.handler_error",
            method=request.method,
            error=str(exc),
            connection_id=state.connection_id,
        )
        resp = create_error_response(
            code=INTERNAL_ERROR,
            message=str(exc),
            request_id=request.id,
        )
        await ws.send_json(resp)


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------


async def websocket_endpoint(ws: WebSocket) -> None:
    """Main WebSocket endpoint: accept, loop receive, handle, disconnect."""
    state = await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            await handle_message(ws, raw, state)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(state.connection_id)
        from nobla.persona.service import cleanup_session
        cleanup_session(state.connection_id)

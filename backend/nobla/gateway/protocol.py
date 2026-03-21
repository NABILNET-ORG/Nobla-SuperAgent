"""
JSON-RPC 2.0 Protocol Models and Parser.

Implements the JSON-RPC 2.0 specification for WebSocket communication
between the Flutter app and the Nobla Gateway.

Reference: https://www.jsonrpc.org/specification
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Standard JSON-RPC 2.0 Error Codes
# ---------------------------------------------------------------------------

PARSE_ERROR: int = -32700
INVALID_REQUEST: int = -32600
METHOD_NOT_FOUND: int = -32601
INVALID_PARAMS: int = -32602
INTERNAL_ERROR: int = -32603

# ---------------------------------------------------------------------------
# Custom Nobla Error Codes
# ---------------------------------------------------------------------------

PROVIDER_UNAVAILABLE: int = -32001
ALL_PROVIDERS_FAILED: int = -32002
RATE_LIMITED: int = -32003
CONVERSATION_NOT_FOUND: int = -32004

# Voice pipeline errors
VOICE_SESSION_EXISTS: int = -32010
VOICE_NO_SESSION: int = -32011
VOICE_ENGINE_UNAVAILABLE: int = -32012

# Human-readable descriptions for standard codes
_ERROR_MESSAGES: dict[int, str] = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid Request",
    METHOD_NOT_FOUND: "Method not found",
    INVALID_PARAMS: "Invalid params",
    INTERNAL_ERROR: "Internal error",
    PROVIDER_UNAVAILABLE: "LLM provider unavailable",
    ALL_PROVIDERS_FAILED: "All LLM providers failed",
    RATE_LIMITED: "Rate limit exceeded",
    CONVERSATION_NOT_FOUND: "Conversation not found",
    VOICE_SESSION_EXISTS: "Voice session already exists",
    VOICE_NO_SESSION: "No active voice session",
    VOICE_ENGINE_UNAVAILABLE: "Voice engine unavailable",
}

JSONRPC_VERSION = "2.0"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class JsonRpcRequest:
    """
    Represents a JSON-RPC 2.0 request (has an id, expects a response).

    Example wire format:
        {"jsonrpc": "2.0", "method": "chat.send", "params": {"message": "hi"}, "id": 1}
    """

    method: str
    id: Any  # str | int | None per spec
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "method": self.method,
            "params": self.params,
            "id": self.id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class JsonRpcNotification:
    """
    Represents a JSON-RPC 2.0 notification (no id, no response expected).

    Used for server-push events such as streaming chat chunks.

    Example wire format:
        {"jsonrpc": "2.0", "method": "chat.stream", "params": {"chunk": "hi", "done": false}}
    """

    method: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # Notifications MUST NOT include the "id" member per spec.
        return {
            "jsonrpc": JSONRPC_VERSION,
            "method": self.method,
            "params": self.params,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class JsonRpcResponse:
    """
    Represents a JSON-RPC 2.0 success response.

    Example wire format:
        {"jsonrpc": "2.0", "result": {"message": "hello"}, "id": 1}
    """

    result: Any
    id: Any

    def to_dict(self) -> dict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "result": self.result,
            "id": self.id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class JsonRpcError:
    """
    Represents a JSON-RPC 2.0 error (either a protocol error or a response error).

    Dual role:
    - When returned from parse_message(), it signals a parse/validation failure
      before a full request could be constructed.
    - When used as a response, it carries the error back to the caller.

    Example wire format:
        {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": null}
    """

    code: int
    message: str
    data: Any = None  # Optional additional information
    id: Any = None   # May be null when id could not be determined

    def to_dict(self) -> dict:
        error_obj: dict = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            error_obj["data"] = self.data

        return {
            "jsonrpc": JSONRPC_VERSION,
            "error": error_obj,
            "id": self.id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_message(raw: str) -> JsonRpcRequest | JsonRpcError:
    """
    Parse a raw JSON string into a JsonRpcRequest.

    Returns a JsonRpcError if the message cannot be parsed or is invalid:
    - PARSE_ERROR  (-32700): raw string is not valid JSON
    - INVALID_REQUEST (-32600): JSON is valid but missing required fields

    Args:
        raw: Raw JSON string received over WebSocket.

    Returns:
        JsonRpcRequest on success, JsonRpcError on failure.
    """
    # 1. Attempt JSON decode
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return JsonRpcError(
            code=PARSE_ERROR,
            message=_ERROR_MESSAGES[PARSE_ERROR],
            id=None,
        )

    # 2. Must be a dict (object)
    if not isinstance(data, dict):
        return JsonRpcError(
            code=INVALID_REQUEST,
            message=_ERROR_MESSAGES[INVALID_REQUEST],
            id=None,
        )

    # Extract id early so we can attach it to error responses
    request_id = data.get("id")

    # 3. Validate jsonrpc version (be lenient — only check if present)
    version = data.get("jsonrpc")
    if version is not None and version != JSONRPC_VERSION:
        return JsonRpcError(
            code=INVALID_REQUEST,
            message=_ERROR_MESSAGES[INVALID_REQUEST],
            data={"detail": f"Unsupported jsonrpc version: {version}"},
            id=request_id,
        )

    # 4. method is required
    method = data.get("method")
    if not method or not isinstance(method, str):
        return JsonRpcError(
            code=INVALID_REQUEST,
            message=_ERROR_MESSAGES[INVALID_REQUEST],
            data={"detail": "Missing or invalid 'method' field"},
            id=request_id,
        )

    # 5. params is optional; default to empty dict
    params = data.get("params", {})
    if not isinstance(params, (dict, list)):
        return JsonRpcError(
            code=INVALID_PARAMS,
            message=_ERROR_MESSAGES[INVALID_PARAMS],
            data={"detail": "'params' must be an object or array"},
            id=request_id,
        )
    # Normalise list params to dict for internal consistency
    if isinstance(params, list):
        params = {"args": params}

    return JsonRpcRequest(
        method=method,
        id=request_id,
        params=params,
    )


# ---------------------------------------------------------------------------
# Response Factories
# ---------------------------------------------------------------------------


def create_error_response(
    code: int,
    message: str,
    data: Any = None,
    request_id: Any = None,
) -> dict:
    """
    Build a JSON-RPC 2.0 error response dict ready for serialisation.

    Args:
        code: JSON-RPC error code (use constants defined in this module).
        message: Human-readable error description.
        data: Optional additional error details.
        request_id: The id from the originating request (may be None).

    Returns:
        Dict conforming to the JSON-RPC 2.0 error response format.
    """
    err = JsonRpcError(code=code, message=message, data=data, id=request_id)
    return err.to_dict()


def create_success_response(result: Any, request_id: Any) -> dict:
    """
    Build a JSON-RPC 2.0 success response dict ready for serialisation.

    Args:
        result: The value to return to the caller.
        request_id: The id from the originating request.

    Returns:
        Dict conforming to the JSON-RPC 2.0 success response format.
    """
    resp = JsonRpcResponse(result=result, id=request_id)
    return resp.to_dict()

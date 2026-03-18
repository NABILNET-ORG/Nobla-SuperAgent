import pytest
from nobla.gateway.protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    JsonRpcNotification, parse_message, create_error_response,
    create_success_response,
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND,
)


def test_parse_valid_request():
    raw = '{"jsonrpc": "2.0", "method": "chat.send", "params": {"message": "hi"}, "id": 1}'
    msg = parse_message(raw)
    assert isinstance(msg, JsonRpcRequest)
    assert msg.method == "chat.send"
    assert msg.params["message"] == "hi"
    assert msg.id == 1


def test_parse_invalid_json():
    msg = parse_message("not json{")
    assert isinstance(msg, JsonRpcError)
    assert msg.code == PARSE_ERROR


def test_parse_missing_method():
    msg = parse_message('{"jsonrpc": "2.0", "id": 1}')
    assert isinstance(msg, JsonRpcError)
    assert msg.code == INVALID_REQUEST


def test_create_error_response():
    resp = create_error_response(METHOD_NOT_FOUND, "Method not found", request_id=1)
    assert resp["jsonrpc"] == "2.0"
    assert resp["error"]["code"] == METHOD_NOT_FOUND
    assert resp["id"] == 1


def test_notification_has_no_id():
    notif = JsonRpcNotification(method="chat.stream", params={"chunk": "hi", "done": False})
    d = notif.to_dict()
    assert "id" not in d
    assert d["method"] == "chat.stream"


def test_create_success_response():
    resp = create_success_response({"message": "hello"}, request_id=42)
    assert resp["jsonrpc"] == "2.0"
    assert resp["result"]["message"] == "hello"
    assert resp["id"] == 42


def test_response_to_json():
    resp = JsonRpcResponse(result={"ok": True}, id=1)
    j = resp.to_json()
    assert '"ok": true' in j


def test_error_to_json_with_data():
    err = JsonRpcError(code=-32600, message="bad", data={"detail": "missing"}, id=1)
    d = err.to_dict()
    assert d["error"]["data"]["detail"] == "missing"

import pytest
from nobla.gateway.protocol import JsonRpcRequest
from nobla.gateway.websocket import _method_registry


def test_conversation_list_method_registered():
    assert "conversation.list" in _method_registry


def test_conversation_get_method_registered():
    assert "conversation.get" in _method_registry


def test_conversation_create_method_registered():
    assert "conversation.create" in _method_registry


def test_conversation_archive_method_registered():
    assert "conversation.archive" in _method_registry


def test_conversation_rename_method_registered():
    assert "conversation.rename" in _method_registry


def test_conversation_search_method_registered():
    assert "conversation.search" in _method_registry


def test_conversation_pause_method_registered():
    assert "conversation.pause" in _method_registry


def test_conversation_list_request_format():
    req = JsonRpcRequest(method="conversation.list", params={}, id=1)
    assert req.method == "conversation.list"


def test_conversation_get_request_format():
    req = JsonRpcRequest(
        method="conversation.get",
        params={"conversation_id": "test-uuid"},
        id=2,
    )
    assert req.params["conversation_id"] == "test-uuid"


def test_conversation_search_request_format():
    req = JsonRpcRequest(
        method="conversation.search",
        params={"query": "python deployment"},
        id=3,
    )
    assert req.params["query"] == "python deployment"

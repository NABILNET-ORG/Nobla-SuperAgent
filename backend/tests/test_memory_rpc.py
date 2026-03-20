"""Tests for memory RPC method registration."""

import pytest
from nobla.gateway.websocket import _method_registry

# Import to trigger registration
import nobla.gateway.memory_handlers  # noqa: F401


def test_memory_stats_registered():
    assert "memory.stats" in _method_registry


def test_memory_facts_registered():
    assert "memory.facts" in _method_registry


def test_memory_graph_registered():
    assert "memory.graph" in _method_registry


def test_memory_search_registered():
    assert "memory.search" in _method_registry


def test_memory_procedures_registered():
    assert "memory.procedures" in _method_registry

import pytest
from nobla.memory.working import WorkingMemory


@pytest.fixture
def wm():
    return WorkingMemory(max_tokens=1000)


def test_add_message(wm):
    wm.add_message("user", "Hello world")
    assert len(wm.messages) == 1


def test_get_context_within_budget(wm):
    wm.add_message("user", "Hello")
    wm.add_message("assistant", "Hi there!")
    ctx = wm.get_context(system_prompt="You are Nobla.", memory_block="")
    assert "Hello" in ctx
    assert "Hi there!" in ctx


def test_context_respects_token_budget():
    wm = WorkingMemory(max_tokens=50)
    for i in range(20):
        wm.add_message("user", f"This is message number {i} with some extra words")
    ctx = wm.get_context(system_prompt="System.", memory_block="")
    # Should truncate older messages
    assert "message number 19" in ctx  # Most recent kept


def test_observation_masking(wm):
    wm.add_message("assistant", "Running code...", tool_output="x = 1\n>>> 1")
    ctx = wm.get_context(system_prompt="", memory_block="")
    assert "Running code..." in ctx
    assert ">>> 1" not in ctx  # Tool output masked


def test_clear(wm):
    wm.add_message("user", "test")
    wm.clear()
    assert len(wm.messages) == 0


def test_rolling_summary_placeholder(wm):
    """Rolling summary is set externally by the warm path."""
    wm.set_rolling_summary("Previously discussed Python deployment.")
    ctx = wm.get_context(system_prompt="", memory_block="")
    assert "Previously discussed" in ctx

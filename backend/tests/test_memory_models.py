import pytest
from nobla.db.models.conversations import Conversation, Message
from nobla.db.models.memory import MemoryNode, Procedure


def test_conversation_has_summary_field():
    """Verify summary column exists on Conversation model."""
    assert hasattr(Conversation, "summary")


def test_conversation_has_topics_field():
    assert hasattr(Conversation, "topics")


def test_conversation_has_message_count_field():
    assert hasattr(Conversation, "message_count")


def test_message_has_parent_message_id():
    assert hasattr(Message, "parent_message_id")


def test_message_has_entities_extracted():
    assert hasattr(Message, "entities_extracted")


def test_memory_node_has_source_conversation_ids():
    assert hasattr(MemoryNode, "source_conversation_ids")


def test_memory_node_has_decay_factor():
    assert hasattr(MemoryNode, "decay_factor")


def test_procedure_has_beta_success():
    assert hasattr(Procedure, "beta_success")


def test_procedure_has_beta_failure():
    assert hasattr(Procedure, "beta_failure")


def test_procedure_has_trigger_context():
    assert hasattr(Procedure, "trigger_context")


def test_procedure_has_last_triggered():
    assert hasattr(Procedure, "last_triggered")

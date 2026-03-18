import pytest
from nobla.db.repositories import ConversationRepository, UsageRepository


def test_conversation_repo_importable():
    """ConversationRepository should be importable."""
    assert ConversationRepository is not None
    assert hasattr(ConversationRepository, 'create_conversation')
    assert hasattr(ConversationRepository, 'get_conversation')
    assert hasattr(ConversationRepository, 'list_conversations')
    assert hasattr(ConversationRepository, 'add_message')
    assert hasattr(ConversationRepository, 'get_recent_messages')


def test_usage_repo_importable():
    """UsageRepository should be importable."""
    assert UsageRepository is not None
    assert hasattr(UsageRepository, 'log_usage')
    assert hasattr(UsageRepository, 'get_total_cost')


def test_repos_require_session():
    """Repositories should require a session argument."""
    import inspect
    sig = inspect.signature(ConversationRepository.__init__)
    assert 'session' in sig.parameters
    sig2 = inspect.signature(UsageRepository.__init__)
    assert 'session' in sig2.parameters

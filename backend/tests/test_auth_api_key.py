import pytest
from cryptography.fernet import InvalidToken

from nobla.brain.auth.api_key import ApiKeyManager, ApiKeyRecord


@pytest.fixture
def manager():
    return ApiKeyManager(encryption_key="test-secret-key-32bytes-padding!")


def test_store_and_retrieve_key(manager):
    manager.store("openai", "user-1", "sk-test-key-12345")
    record = manager.get("openai", "user-1")
    assert record is not None
    assert record.provider == "openai"
    assert record.user_id == "user-1"
    assert record.api_key == "sk-test-key-12345"


def test_get_nonexistent_returns_none(manager):
    assert manager.get("openai", "user-1") is None


def test_delete_key(manager):
    manager.store("openai", "user-1", "sk-test-key")
    manager.delete("openai", "user-1")
    assert manager.get("openai", "user-1") is None


def test_key_is_encrypted_in_storage(manager):
    manager.store("openai", "user-1", "sk-test-key-12345")
    raw = manager._get_raw("openai", "user-1")
    assert raw != "sk-test-key-12345"
    assert raw is not None


def test_validate_openai_key_format(manager):
    assert manager.validate_format("openai", "sk-proj-abc12345678901234567") is True
    assert manager.validate_format("openai", "not-a-valid-key") is False


def test_validate_anthropic_key_format(manager):
    assert manager.validate_format("anthropic", "sk-ant-abc12345678901234567") is True
    assert manager.validate_format("anthropic", "bad") is False


def test_validate_groq_key_format(manager):
    assert manager.validate_format("groq", "gsk_abc12345678901234567890") is True
    assert manager.validate_format("groq", "bad") is False


def test_validate_unknown_provider_accepts_any(manager):
    assert manager.validate_format("unknown", "anything") is True


def test_list_providers_for_user(manager):
    manager.store("openai", "user-1", "sk-test-11111111111111111111")
    manager.store("groq", "user-1", "gsk_test222222222222222222222")
    providers = manager.list_providers("user-1")
    assert set(providers) == {"openai", "groq"}


def test_wrong_encryption_key_cannot_decrypt():
    mgr1 = ApiKeyManager(encryption_key="secret-key-one-32bytes-padding!!")
    mgr1.store("openai", "user-1", "sk-real-key-123456789012")
    raw = mgr1._store.get(("openai", "user-1"))
    mgr2 = ApiKeyManager(encryption_key="secret-key-two-32bytes-padding!!")
    with pytest.raises(InvalidToken):
        mgr2._fernet.decrypt(raw)


def test_store_empty_key(manager):
    manager.store("openai", "user-1", "")
    record = manager.get("openai", "user-1")
    assert record is not None
    assert record.api_key == ""

import pytest
from nobla.security.auth import AuthService


@pytest.fixture
def auth():
    return AuthService(secret_key="test-secret", access_expire_minutes=60, refresh_expire_days=7, bcrypt_rounds=4)


def test_hash_and_verify_passphrase(auth):
    hashed = auth.hash_passphrase("mypassphrase")
    assert auth.verify_passphrase("mypassphrase", hashed) is True
    assert auth.verify_passphrase("wrong", hashed) is False


def test_create_access_token(auth):
    token = auth.create_access_token(user_id="user-123")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_token(auth):
    token = auth.create_refresh_token(user_id="user-123")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_decode_invalid_token(auth):
    result = auth.decode_token("invalid.token.here")
    assert result is None


def test_decode_expired_token(auth):
    svc = AuthService(secret_key="test", access_expire_minutes=-1, refresh_expire_days=7, bcrypt_rounds=4)
    token = svc.create_access_token(user_id="user-123")
    assert svc.decode_token(token) is None


def test_validate_passphrase_too_short(auth):
    assert auth.validate_passphrase("short") == False
    assert auth.validate_passphrase("longenough") == True

import pytest

from nobla.brain.auth.oauth import OAuthManager, OAuthConfig, OAuthTokens


@pytest.fixture
def oauth_manager():
    configs = {
        "gemini": OAuthConfig(
            provider="gemini",
            client_id="test-client-id",
            client_secret="test-client-secret",
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/generative-language"],
            redirect_uri="http://localhost:8000/api/oauth/callback/gemini",
        ),
    }
    return OAuthManager(configs=configs, encryption_key="test-key-32bytes-padding!!")


def test_get_auth_url_with_state(oauth_manager):
    url, state = oauth_manager.get_auth_url("gemini", "user-1")
    assert "accounts.google.com" in url
    assert "client_id=test-client-id" in url
    assert f"state={state}" in url
    assert len(state) > 10


def test_get_auth_url_unknown_provider(oauth_manager):
    with pytest.raises(ValueError, match="No OAuth config"):
        oauth_manager.get_auth_url("unknown", "user-1")


def test_validate_state(oauth_manager):
    _, state = oauth_manager.get_auth_url("gemini", "user-1")
    user_id = oauth_manager.validate_state(state)
    assert user_id == "user-1"


def test_validate_invalid_state(oauth_manager):
    assert oauth_manager.validate_state("invalid-state") is None


def test_store_and_get_tokens(oauth_manager):
    tokens = OAuthTokens(
        access_token="ya29.access",
        refresh_token="1//refresh",
        expires_at=9999999999,
        provider="gemini",
    )
    oauth_manager.store_tokens("gemini", "user-1", tokens)
    retrieved = oauth_manager.get_tokens("gemini", "user-1")
    assert retrieved is not None
    assert retrieved.access_token == "ya29.access"


def test_get_tokens_nonexistent(oauth_manager):
    assert oauth_manager.get_tokens("gemini", "user-1") is None


def test_revoke_tokens(oauth_manager):
    tokens = OAuthTokens(
        access_token="ya29.test",
        refresh_token="1//test",
        expires_at=9999999999,
        provider="gemini",
    )
    oauth_manager.store_tokens("gemini", "user-1", tokens)
    oauth_manager.revoke("gemini", "user-1")
    assert oauth_manager.get_tokens("gemini", "user-1") is None


def test_is_expired():
    expired = OAuthTokens(
        access_token="t", refresh_token="t", expires_at=0, provider="gemini"
    )
    assert expired.is_expired is True
    valid = OAuthTokens(
        access_token="t", refresh_token="t", expires_at=9999999999, provider="gemini"
    )
    assert valid.is_expired is False


def test_supported_providers(oauth_manager):
    assert "gemini" in oauth_manager.supported_providers()


def test_csrf_state_is_single_use(oauth_manager):
    _, state = oauth_manager.get_auth_url("gemini", "user-1")
    assert oauth_manager.validate_state(state) == "user-1"
    assert oauth_manager.validate_state(state) is None  # Replay rejected


def test_auth_url_includes_csrf_state(oauth_manager):
    url, state = oauth_manager.get_auth_url("gemini", "user-1")
    assert f"state={state}" in url
    assert "access_type=offline" in url

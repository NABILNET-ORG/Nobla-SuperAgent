"""JSON-RPC handlers for provider management."""

from __future__ import annotations
import structlog
from nobla.gateway.websocket import rpc_method, ConnectionState

logger = structlog.get_logger(__name__)

_api_key_manager = None
_oauth_manager = None
_local_model_manager = None
_provider_registry: dict[str, dict] = {}


def set_api_key_manager(mgr) -> None:
    global _api_key_manager
    _api_key_manager = mgr


def set_oauth_manager(mgr) -> None:
    global _oauth_manager
    _oauth_manager = mgr


def set_local_model_manager(mgr) -> None:
    global _local_model_manager
    _local_model_manager = mgr


def set_provider_registry(registry: dict[str, dict]) -> None:
    global _provider_registry
    _provider_registry = registry


@rpc_method("provider.list")
async def handle_provider_list(params: dict, state: ConnectionState) -> dict:
    providers = []
    for name, info in _provider_registry.items():
        connected = False
        auth_type = "none"
        if _api_key_manager and _api_key_manager.get(name, state.user_id or ""):
            connected = True
            auth_type = "api_key"
        elif _oauth_manager and _oauth_manager.get_tokens(name, state.user_id or ""):
            connected = True
            auth_type = "oauth"
        elif _local_model_manager and name == "ollama":
            endpoint = _local_model_manager.get(state.user_id or "")
            if endpoint:
                connected = True
                auth_type = "local"
        providers.append({
            "name": name,
            "display_name": info.get("display_name", name.title()),
            "connected": connected,
            "auth_type": auth_type,
            "auth_methods": info.get("auth_methods", ["api_key"]),
            "model": info.get("model", ""),
        })
    return {"providers": providers}


@rpc_method("provider.connect_apikey")
async def handle_provider_connect_apikey(params: dict, state: ConnectionState) -> dict:
    if not _api_key_manager:
        raise RuntimeError("API key manager not initialized")
    provider = params.get("provider", "")
    api_key = params.get("api_key", "")
    if not provider or not api_key:
        return {"connected": False, "error": "Provider and api_key are required"}
    if not _api_key_manager.validate_format(provider, api_key):
        return {"connected": False, "error": f"Invalid API key format for {provider}"}
    user_id = state.user_id or "default"
    _api_key_manager.store(provider, user_id, api_key)
    return {"connected": True, "provider": provider, "auth_type": "api_key"}


@rpc_method("provider.oauth_url")
async def handle_provider_oauth_url(params: dict, state: ConnectionState) -> dict:
    if not _oauth_manager:
        raise RuntimeError("OAuth manager not initialized")
    provider = params.get("provider", "")
    user_id = state.user_id or "default"
    try:
        url, oauth_state = _oauth_manager.get_auth_url(provider, user_id)
        return {"auth_url": url, "state": oauth_state}
    except ValueError as e:
        return {"error": str(e)}


@rpc_method("provider.oauth_callback")
async def handle_provider_oauth_callback(params: dict, state: ConnectionState) -> dict:
    if not _oauth_manager:
        raise RuntimeError("OAuth manager not initialized")
    oauth_state = params.get("state", "")
    user_id = _oauth_manager.validate_state(oauth_state)
    if not user_id:
        return {"connected": False, "error": "Invalid or expired OAuth state (CSRF check failed)"}
    return {"connected": True, "user_id": user_id, "message": "OAuth code received; token exchange pending"}


@rpc_method("provider.connect_local")
async def handle_provider_connect_local(params: dict, state: ConnectionState) -> dict:
    if not _local_model_manager:
        raise RuntimeError("Local model manager not initialized")
    base_url = params.get("base_url", "http://localhost:11434")
    models = params.get("models", [])
    user_id = state.user_id or "default"
    endpoint = _local_model_manager.register(user_id, base_url, models)
    return {"connected": True, "base_url": endpoint.base_url, "models": endpoint.models}


@rpc_method("provider.disconnect")
async def handle_provider_disconnect(params: dict, state: ConnectionState) -> dict:
    provider = params.get("provider", "")
    user_id = state.user_id or "default"
    if _api_key_manager:
        _api_key_manager.delete(provider, user_id)
    if _oauth_manager:
        _oauth_manager.revoke(provider, user_id)
    if _local_model_manager and provider == "ollama":
        _local_model_manager.remove(user_id)
    return {"disconnected": True, "provider": provider}


@rpc_method("provider.health")
async def handle_provider_health(params: dict, state: ConnectionState) -> dict:
    from nobla.gateway.websocket import get_router
    provider_name = params.get("provider", "")
    router = get_router()
    if not router:
        return {"healthy": False, "error": "Router not initialized"}
    provider = router.providers.get(provider_name)
    if not provider:
        return {"healthy": False, "error": f"Provider '{provider_name}' not configured"}
    try:
        healthy = await provider.health_check()
        return {"healthy": healthy, "provider": provider_name}
    except Exception as e:
        return {"healthy": False, "error": str(e)}

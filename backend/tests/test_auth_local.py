import pytest

from nobla.brain.auth.local import LocalModelManager, LocalEndpoint


@pytest.fixture
def manager():
    return LocalModelManager()


def test_register_endpoint(manager):
    manager.register("user-1", "http://localhost:11434")
    endpoint = manager.get("user-1")
    assert endpoint is not None
    assert endpoint.base_url == "http://localhost:11434"


def test_register_with_models(manager):
    manager.register("user-1", "http://localhost:11434", models=["llama3.1", "codellama"])
    endpoint = manager.get("user-1")
    assert endpoint.models == ["llama3.1", "codellama"]


def test_get_nonexistent(manager):
    assert manager.get("user-1") is None


def test_remove_endpoint(manager):
    manager.register("user-1", "http://localhost:11434")
    manager.remove("user-1")
    assert manager.get("user-1") is None


def test_update_models(manager):
    manager.register("user-1", "http://localhost:11434", models=["llama3.1"])
    manager.update_models("user-1", ["llama3.1", "codellama", "mistral"])
    endpoint = manager.get("user-1")
    assert len(endpoint.models) == 3


def test_default_url():
    manager = LocalModelManager(default_url="http://gpu-box:11434")
    assert manager.default_url == "http://gpu-box:11434"

import pytest
from src.backends.router import ModelRouter
from src.config import AppConfig, ProfileConfig


@pytest.fixture
def test_config():
    config = AppConfig()
    config.profiles["test-profile"] = ProfileConfig(
        backend="mock",
        model="test-model",
        mode="test-mode",
        description="A test profile",
    )
    return config


def test_router_configured_profile(test_config):
    router = ModelRouter(test_config)
    backend, kwargs, overrides = router.resolve("test-profile")
    assert backend.name == "mock"
    assert kwargs.get("model") == "test-model"
    assert kwargs.get("mode") == "test-mode"


def test_router_dynamic_agy_parsing(test_config):
    router = ModelRouter(test_config)

    # Base agy
    b, kw, _ = router.resolve("agy")
    assert b.name == "agy"
    assert "model" not in kw

    # agy with mode
    b, kw, _ = router.resolve("agy:plan")
    assert b.name == "agy"
    assert kw.get("mode") == "plan"

    b, kw, _ = router.resolve("agy:accept-edits")
    assert b.name == "agy"
    assert kw.get("mode") == "accept-edits"

    # agy with specific model
    b, kw, _ = router.resolve("agy:gemini-3.8-flash-high")
    assert b.name == "agy"
    assert kw.get("model") == "gemini-3.8-flash-high"


def test_router_dynamic_codex_parsing(test_config):
    router = ModelRouter(test_config)

    # Default codex
    b, kw, _ = router.resolve("codex")
    assert b.name == "codex"
    assert kw.get("sandbox") == "read-only"

    # Codex write sandbox
    b, kw, _ = router.resolve("codex:workspace-write")
    assert b.name == "codex"
    assert kw.get("sandbox") == "workspace-write"

    b, kw, _ = router.resolve("codex:danger-full-access")
    assert b.name == "codex"
    assert kw.get("sandbox") == "danger-full-access"


def test_router_mock_and_fallback(test_config):
    router = ModelRouter(test_config)

    # Mock prefix
    b, _, _ = router.resolve("mock")
    assert b.name == "mock"

    # Direct model name prefix
    b, kw, _ = router.resolve("claude-sonnet-4-6")
    assert b.name == "agy"
    assert kw.get("model") == "claude-sonnet-4-6"

    # Unknown fallback
    b, _, _ = router.resolve("unknown-custom-model")
    assert b.name == "agy"


@pytest.mark.asyncio
async def test_router_get_all_models(test_config):
    test_config.backends.agy.auto_discover_models = False
    router = ModelRouter(test_config)
    models = await router.get_all_models()
    names = [m.name for m in models]
    assert "agy:latest" in names
    assert "codex:latest" in names
    assert "mock" in names
    assert "test-profile" in names

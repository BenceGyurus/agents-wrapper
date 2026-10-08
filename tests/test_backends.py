import pytest
from src.backends.base import BaseBackend, BackendExecutionError
from src.backends.mock import MockBackend
from src.backends.agy import AntigravityBackend
from src.backends.codex import CodexBackend


@pytest.mark.asyncio
async def test_mock_backend_generate():
    backend = MockBackend()
    res = await backend.generate("Hello test")
    assert "Mock response from" in res
    assert "All pipeline checks passed successfully!" in res


def test_agy_backend_missing_binary():
    backend = AntigravityBackend(config={"binary_path": "non_existent_binary_xyz"})
    with pytest.raises(BackendExecutionError) as exc_info:
        backend._resolve_binary()
    assert "not found in PATH" in str(exc_info.value)


def test_codex_backend_missing_binary():
    backend = CodexBackend(config={"binary_path": "non_existent_binary_xyz"})
    with pytest.raises(BackendExecutionError) as exc_info:
        backend._resolve_binary()
    assert "not found in PATH" in str(exc_info.value)

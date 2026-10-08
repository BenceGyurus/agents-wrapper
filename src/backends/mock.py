import asyncio
from typing import Any, AsyncIterator, Dict
from src.backends.base import BaseBackend


class MockBackend(BaseBackend):
    """Simulates agent responses for fast offline testing and verification."""

    def __init__(self, name: str = "mock", config: Dict[str, Any] = None):
        super().__init__(name, config)

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        tokens = [
            "Mock response from ",
            f"backend '{self.name}'",
            ": Processing prompt: ",
            f"'{prompt[:40]}...'. ",
            "All pipeline checks passed successfully!",
        ]
        for token in tokens:
            await asyncio.sleep(0.05)
            yield token

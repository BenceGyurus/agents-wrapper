from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict


class BackendExecutionError(Exception):
    """Raised when backend CLI execution fails."""
    pass


class BaseBackend(ABC):
    """Abstract interface for CLI agent execution backends."""

    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Streams text chunks in real-time from the CLI process."""
        pass

    async def generate(self, prompt: str, **kwargs) -> str:
        """Executes the CLI process and returns the full aggregated response."""
        chunks = []
        async for chunk in self.stream(prompt, **kwargs):
            chunks.append(chunk)
        return "".join(chunks)

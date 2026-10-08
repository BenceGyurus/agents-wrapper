from abc import ABC, abstractmethod
from typing import Any, Dict
from src.pipeline.context import PipelineContext


class BaseLayer(ABC):
    """Base class for all pipeline interceptor layers."""

    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        """Called before the request is dispatched to the backend CLI.
        Can modify the prompt, inject context, or abort the request.
        """
        return ctx

    async def post_process_chunk(self, chunk: str, ctx: PipelineContext) -> str:
        """Called for each streamed chunk of text from the backend CLI.
        Allows real-time masking or token inspection.
        """
        return chunk

    async def post_process_full(self, full_response: str, ctx: PipelineContext) -> str:
        """Called after the full response has been generated.
        Allows logging, auditing, or post-generation validation.
        """
        return full_response

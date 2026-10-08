import logging
from typing import Dict, List, Type
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext
from src.pipeline.layers import (
    SecurityLayer,
    PromptSanitizerLayer,
    AuditLayer,
    ExternalHookLayer,
    MultimodalImageLayer,
)
from src.config import PipelineConfig

logger = logging.getLogger("wrapper.pipeline")


class PipelineRunner:
    """Orchestrates layer execution for pre-processing, chunk transforms, and post-processing."""

    # Built-in layer registry
    REGISTRY: Dict[str, Type[BaseLayer]] = {
        "security_check": SecurityLayer,
        "multimodal_image": MultimodalImageLayer,
        "prompt_sanitizer": PromptSanitizerLayer,
        "audit_logger": AuditLayer,
        "external_hook": ExternalHookLayer,
    }

    def __init__(self, layers: List[BaseLayer]):
        self.layers = layers

    @classmethod
    def register_layer_class(cls, name: str, layer_class: Type[BaseLayer]) -> None:
        """Dynamically register custom layer classes."""
        cls.REGISTRY[name] = layer_class

    @classmethod
    def from_config(cls, pipeline_config: PipelineConfig, overrides: Dict = None) -> "PipelineRunner":
        """Builds a pipeline from configuration, applying optional per-profile overrides."""
        instantiated_layers: List[BaseLayer] = []
        overrides = overrides or {}

        for item in pipeline_config.layers:
            layer_name = item.name
            override_cfg = overrides.get(layer_name, {})
            
            # Check enabled state
            is_enabled = override_cfg.get("enabled", item.enabled)
            if not is_enabled:
                continue

            merged_config = {**item.config, **override_cfg.get("config", {})}
            layer_class = cls.REGISTRY.get(layer_name)

            if layer_class:
                instantiated_layers.append(layer_class(name=layer_name, config=merged_config))
            else:
                logger.warning(f"Unknown pipeline layer '{layer_name}', skipping.")

        return cls(instantiated_layers)

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        """Executes all pre-processing hooks. Short-circuits immediately if aborted."""
        for layer in self.layers:
            ctx = await layer.pre_process(ctx)
            if ctx.aborted:
                logger.info(f"Pipeline short-circuited by layer '{layer.name}': {ctx.abort_reason}")
                break
        return ctx

    async def post_process_chunk(self, chunk: str, ctx: PipelineContext) -> str:
        """Applies chunk transformations in order."""
        for layer in self.layers:
            chunk = await layer.post_process_chunk(chunk, ctx)
        return chunk

    async def post_process_full(self, full_response: str, ctx: PipelineContext) -> str:
        """Executes all post-processing hooks."""
        for layer in self.layers:
            full_response = await layer.post_process_full(full_response, ctx)
        return full_response

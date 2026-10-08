import logging
import httpx
from typing import Any, Dict
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext

logger = logging.getLogger("wrapper.external_hook")


class ExternalHookLayer(BaseLayer):
    """Integrates with 3rd-party external RAG or moderation services via HTTP webhook."""

    def __init__(self, name: str = "external_hook", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.webhook_url = self.config.get("webhook_url", "").strip()
        self.timeout_seconds = self.config.get("timeout_seconds", 5.0)

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        if not self.webhook_url:
            return ctx

        payload = {
            "model": ctx.model,
            "prompt": ctx.prompt_text,
            "system_prompt": ctx.system_prompt,
            "metadata": ctx.metadata,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(self.webhook_url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    # Check if external service wants to abort
                    if data.get("abort"):
                        reason = data.get("abort_reason", "External hook rejected request")
                        ctx.abort(reason, status_code=400)
                        return ctx
                    
                    # Check if external RAG service returned context
                    if "context" in data:
                        ctx.injected_context.append(str(data["context"]))
                    elif "documents" in data and isinstance(data["documents"], list):
                        ctx.injected_context.extend([str(d) for d in data["documents"]])
                else:
                    logger.warning(f"External hook returned non-200 status: {res.status_code}")
        except Exception as e:
            logger.error(f"External hook call failed: {e}")

        return ctx

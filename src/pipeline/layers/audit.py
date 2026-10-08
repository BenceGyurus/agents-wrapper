import time
import json
import logging
from pathlib import Path
from typing import Any, Dict
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext

logger = logging.getLogger("wrapper.audit")


class AuditLayer(BaseLayer):
    """Logs incoming requests, execution duration, and response metrics for compliance & monitoring."""

    def __init__(self, name: str = "audit_logger", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.log_to_console = self.config.get("log_to_console", True)
        self.log_file = self.config.get("log_file", "audit.log")

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        ctx.metadata["start_time"] = time.time()
        ctx.metadata["prompt_chars"] = len(ctx.prompt_text)
        
        if self.log_to_console:
            logger.info(
                f"[AUDIT] Request started for model='{ctx.model}' "
                f"(prompt_len={len(ctx.prompt_text)} chars)"
            )
        return ctx

    async def post_process_full(self, full_response: str, ctx: PipelineContext) -> str:
        start_time = ctx.metadata.get("start_time", time.time())
        duration_sec = round(time.time() - start_time, 3)
        resp_len = len(full_response)

        audit_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": ctx.model,
            "duration_sec": duration_sec,
            "prompt_chars": ctx.metadata.get("prompt_chars", 0),
            "response_chars": resp_len,
            "aborted": ctx.aborted,
            "abort_reason": ctx.abort_reason,
        }

        if self.log_to_console:
            logger.info(
                f"[AUDIT] Completed model='{ctx.model}' in {duration_sec}s "
                f"(response_len={resp_len} chars)"
            )

        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(audit_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log entry: {e}")

        return full_response

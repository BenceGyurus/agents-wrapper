from typing import Any, Dict
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext


class PromptSanitizerLayer(BaseLayer):
    """Sanitizes and formats messages and prompts into an optimized CLI input structure."""

    def __init__(self, name: str = "prompt_sanitizer", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.strip_excess_whitespace = self.config.get("strip_excess_whitespace", True)
        self.include_system_prefix = self.config.get("include_system_prompt_prefix", True)

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        parts = []

        # 1. System Prompt (includes Open WebUI system instructions or RAG docs injected by Open WebUI)
        if ctx.system_prompt and ctx.system_prompt.strip():
            sys_text = ctx.system_prompt.strip()
            if self.include_system_prefix:
                parts.append(f"### System Instructions:\n{sys_text}\n")
            else:
                parts.append(f"{sys_text}\n")

        # 2. Injected context from external layers/RAG (if any)
        if ctx.injected_context:
            context_block = "\n\n".join(ctx.injected_context)
            parts.append(f"### Additional Context:\n{context_block}\n")

        # 3. Conversation history formatting (if multiple messages are provided)
        if ctx.messages:
            # If there's only 1 user message and no previous turns
            non_system_msgs = [m for m in ctx.messages if m.role.lower() != "system"]
            if len(non_system_msgs) == 1 and non_system_msgs[0].role.lower() == "user":
                parts.append(non_system_msgs[0].content.strip())
            else:
                for msg in non_system_msgs:
                    role_label = msg.role.capitalize()
                    parts.append(f"[{role_label}]:\n{msg.content.strip()}\n")
        elif ctx.prompt_text:
            parts.append(ctx.prompt_text.strip())

        compiled_prompt = "\n".join(parts)
        if self.strip_excess_whitespace:
            compiled_prompt = compiled_prompt.strip()

        ctx.prompt_text = compiled_prompt
        return ctx

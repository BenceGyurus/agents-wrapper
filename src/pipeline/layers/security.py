import re
import logging
from typing import Any, Dict, List, Pattern, Tuple
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext

logger = logging.getLogger("wrapper.security")


class SecurityLayer(BaseLayer):
    """Inspects prompts for prompt injections, leaked secrets, and destructive commands."""

    DEFAULT_INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
        r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
        r"you\s+are\s+now\s+(?:in\s+)?(?:dan|developer|jailbreak|unfiltered)\s+mode",
        r"forget\s+(?:all\s+)?(?:previous|prior|everything)",
        r"system\s+override\s*:",
        r"bypass\s+(?:all\s+)?(?:safety|content|security)\s+filters",
    ]

    DEFAULT_SECRET_PATTERNS = [
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API Key"),
        (r"ghp_[0-9a-zA-Z]{36}", "GitHub Personal Access Token"),
        (r"github_pat_[0-9a-zA-Z_]{22,}", "Fine-grained GitHub Token"),
        (r"(?:api[_-]?key|secret[_-]?key|auth[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "API Secret / Token"),
    ]

    DEFAULT_DESTRUCTIVE_PATTERNS = [
        (r"\brm\s+(?:-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?:\s|$|\*)", "Root filesystem deletion (rm -rf /)"),
        (r"\brm\s+(?:-[a-zA-Z]*f[a-zA-Z]*\s+)?~(?:\s|$|\*)", "Home directory deletion (rm -rf ~)"),
        (r"\bmkfs(?:\.[a-z0-9]+)?\b", "Disk formatting command (mkfs)"),
        (r"\bdd\s+if=.*?of=/dev/[a-z]+", "Raw block device write (dd)"),
        (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Bash fork bomb"),
        (r"\bchmod\s+(?:-R\s+)?777\s+/", "Recursive full root permissions"),
    ]

    def __init__(self, name: str = "security_check", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.block_injection = self.config.get("block_on_prompt_injection", True)
        self.block_secrets = self.config.get("block_on_secret_leak", True)
        self.block_destructive = self.config.get("block_on_destructive_commands", True)

        # Compile regexes
        self.injection_regexes: List[Pattern] = [
            re.compile(p, re.IGNORECASE) for p in self.DEFAULT_INJECTION_PATTERNS
        ]
        
        custom_patterns = self.config.get("custom_blocked_patterns", [])
        for cp in custom_patterns:
            self.injection_regexes.append(re.compile(cp, re.IGNORECASE))

        self.secret_regexes: List[Tuple[Pattern, str]] = [
            (re.compile(p, re.IGNORECASE), desc) for p, desc in self.DEFAULT_SECRET_PATTERNS
        ]

        self.destructive_regexes: List[Tuple[Pattern, str]] = [
            (re.compile(p, re.IGNORECASE), desc) for p, desc in self.DEFAULT_DESTRUCTIVE_PATTERNS
        ]

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        texts = [ctx.prompt_text] if ctx.prompt_text else []
        if ctx.system_prompt:
            texts.append(ctx.system_prompt)
        for m in ctx.messages:
            if m.content:
                texts.append(m.content)

        text_to_check = "\n".join(texts)

        # 1. Prompt Injection Check
        if self.block_injection:
            for regex in self.injection_regexes:
                match = regex.search(text_to_check)
                if match:
                    reason = f"Security Violation: Suspected prompt injection detected ('{match.group(0)[:50]}...')"
                    logger.warning(f"Blocked request due to: {reason}")
                    ctx.abort(reason, status_code=400)
                    return ctx

        # 2. Secret Leak Check
        if self.block_secrets:
            for regex, secret_type in self.secret_regexes:
                match = regex.search(text_to_check)
                if match:
                    reason = f"Security Violation: Potential secret/credential leakage detected ({secret_type})"
                    logger.warning(f"Blocked request due to: {reason}")
                    ctx.abort(reason, status_code=400)
                    return ctx

        # 3. Destructive Command Check
        if self.block_destructive:
            for regex, desc in self.destructive_regexes:
                match = regex.search(text_to_check)
                if match:
                    reason = f"Security Violation: Destructive command pattern detected ({desc})"
                    logger.warning(f"Blocked request due to: {reason}")
                    ctx.abort(reason, status_code=400)
                    return ctx

        return ctx

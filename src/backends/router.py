import asyncio
import logging
import re
import shutil
import time
from typing import Dict, List, Optional, Tuple
from src.backends.base import BaseBackend
from src.backends.agy import AntigravityBackend
from src.backends.codex import CodexBackend
from src.backends.mock import MockBackend
from src.config import AppConfig
from src.schemas.ollama import ModelDetails, ModelInfo

logger = logging.getLogger("wrapper.router")


class ModelRouter:
    """Dynamically resolves model requests to appropriate CLI backends and arguments."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.backends: Dict[str, BaseBackend] = {
            "agy": AntigravityBackend(name="agy", config=config.backends.agy.model_dump()),
            "codex": CodexBackend(name="codex", config=config.backends.codex.model_dump()),
            "mock": MockBackend(name="mock"),
        }

        # Cache for discovered agy models
        self._cached_agy_models: List[str] = []
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 3600.0  # 1 hour

    async def discover_agy_models(self) -> List[str]:
        """Discovers available models by invoking 'agy models'."""
        now = time.time()
        if self._cached_agy_models and (now - self._cache_timestamp < self._cache_ttl):
            return self._cached_agy_models

        binary = shutil.which(self.config.backends.agy.binary_path) or shutil.which("agy")
        if not binary:
            return ["gemini-3.8-flash-high", "gemini-3.7-flash-high", "claude-sonnet-4-6"]

        try:
            proc = await asyncio.create_subprocess_exec(
                binary, "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
            text = stdout.decode("utf-8", errors="replace")
            
            # Parse lines like: "gemini-3.8-flash-high     Gemini 3.8 Flash (High)"
            found = []
            for line in text.splitlines():
                line = re.sub(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏\s]+Fetching available models\.\.\.", "", line).strip()
                if not line:
                    continue
                parts = line.split()
                if parts:
                    model_id = parts[0]
                    if any(prefix in model_id for prefix in ["gemini", "claude", "gpt"]):
                        found.append(model_id)

            if found:
                self._cached_agy_models = found
                self._cache_timestamp = now
                return found
        except Exception as e:
            logger.warning(f"Could not dynamically query 'agy models': {e}")

        # Fallbacks if discovery is unavailable
        default_fallback = [
            "gemini-3.8-flash-high",
            "gemini-3.8-flash-medium",
            "gemini-3.7-flash-high",
            "claude-sonnet-4-6",
            "gpt-oss-120b-medium",
        ]
        self._cached_agy_models = default_fallback
        return default_fallback

    def resolve(self, model_name: str) -> Tuple[BaseBackend, dict, dict]:
        """
        Resolves model name to (backend, backend_kwargs, pipeline_overrides).
        Supports:
          - Explicit profiles from config.yaml
          - Dynamic agy names: 'agy', 'agy:latest', 'agy:gemini-3.8-flash-high', 'agy:plan'
          - Dynamic codex names: 'codex', 'codex:readonly', 'codex:workspace-write'
          - Mock backend: 'mock'
        """
        model_name = (model_name or "agy").strip()

        # 1. Check configured profiles
        if model_name in self.config.profiles:
            profile = self.config.profiles[model_name]
            backend = self.backends.get(profile.backend, self.backends["agy"])
            kwargs = {}
            if profile.model:
                kwargs["model"] = profile.model
            if profile.mode:
                kwargs["mode"] = profile.mode
            if profile.sandbox:
                kwargs["sandbox"] = profile.sandbox
            return backend, kwargs, profile.pipeline_overrides

        # 2. Dynamic 'mock' prefix
        if model_name.startswith("mock"):
            return self.backends["mock"], {}, {}

        # 3. Dynamic 'codex' patterns
        if model_name == "codex" or model_name.startswith("codex:"):
            sandbox = "read-only"
            if ":" in model_name:
                sub = model_name.split(":", 1)[1]
                if sub in ["workspace-write", "write"]:
                    sandbox = "workspace-write"
                elif sub in ["danger-full-access", "full"]:
                    sandbox = "danger-full-access"
            return self.backends["codex"], {"sandbox": sandbox}, {}

        # 4. Dynamic 'agy' patterns (e.g. 'agy', 'agy:plan', 'agy:claude-sonnet-4-6')
        if model_name == "agy" or model_name.startswith("agy:"):
            kwargs = {}
            if ":" in model_name:
                sub = model_name.split(":", 1)[1]
                if sub in ["plan", "accept-edits"]:
                    kwargs["mode"] = sub
                else:
                    kwargs["model"] = sub
            return self.backends["agy"], kwargs, {}

        # 5. Direct model names (e.g. if someone passes 'gemini-3.8-flash-high' or 'claude-sonnet-4-6' directly)
        if any(prefix in model_name for prefix in ["gemini", "claude", "gpt"]):
            return self.backends["agy"], {"model": model_name}, {}

        # Default fallback to agy
        return self.backends["agy"], {}, {}

    async def get_all_models(self) -> List[ModelInfo]:
        """Returns the full list of dynamic and configured models for /api/tags."""
        models: List[ModelInfo] = []

        # Default base entries
        models.append(
            ModelInfo(
                name="agy:latest",
                model="agy:latest",
                digest="agy-latest",
                details=ModelDetails(
                    family="antigravity",
                    parameter_size="agent",
                    quantization_level="cloud",
                ),
            )
        )
        models.append(
            ModelInfo(
                name="agy:plan",
                model="agy:plan",
                digest="agy-plan",
                details=ModelDetails(
                    family="antigravity",
                    parameter_size="planning-mode",
                    quantization_level="cloud",
                ),
            )
        )
        models.append(
            ModelInfo(
                name="codex:latest",
                model="codex:latest",
                digest="codex-latest",
                details=ModelDetails(
                    family="codex",
                    parameter_size="agent",
                    quantization_level="cloud",
                ),
            )
        )
        models.append(
            ModelInfo(
                name="mock",
                model="mock",
                digest="mock-test",
                details=ModelDetails(
                    family="mock",
                    parameter_size="0B",
                    quantization_level="none",
                ),
            )
        )

        # Configured profiles
        for name, profile in self.config.profiles.items():
            models.append(
                ModelInfo(
                    name=name,
                    model=name,
                    digest=f"profile-{name}",
                    details=ModelDetails(
                        family=profile.backend,
                        parameter_size=profile.mode or "agent",
                        quantization_level="configured",
                    ),
                )
            )

        # Dynamically discovered agy models
        if self.config.backends.agy.auto_discover_models:
            agy_models = await self.discover_agy_models()
            for m in agy_models:
                full_name = f"agy:{m}"
                models.append(
                    ModelInfo(
                        name=full_name,
                        model=full_name,
                        digest=f"agy-{m}",
                        details=ModelDetails(
                            family="antigravity",
                            parameter_size=m,
                            quantization_level="cloud",
                        ),
                    )
                )

        return models

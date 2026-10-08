import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 11434
    log_level: str = "info"


class AgyBackendConfig(BaseModel):
    binary_path: str = "agy"
    default_model: str = "gemini-3.8-flash-high"
    default_effort: str = "high"
    auto_discover_models: bool = True
    timeout_seconds: int = 120


class CodexBackendConfig(BaseModel):
    binary_path: str = "codex"
    default_sandbox: str = "read-only"
    timeout_seconds: int = 120


class BackendsConfig(BaseModel):
    agy: AgyBackendConfig = Field(default_factory=AgyBackendConfig)
    codex: CodexBackendConfig = Field(default_factory=CodexBackendConfig)


class LayerConfig(BaseModel):
    name: str
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    layers: List[LayerConfig] = Field(default_factory=list)


class ProfileConfig(BaseModel):
    backend: str
    model: Optional[str] = None
    mode: Optional[str] = None
    sandbox: Optional[str] = None
    description: Optional[str] = None
    pipeline_overrides: Dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    backends: BackendsConfig = Field(default_factory=BackendsConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    profiles: Dict[str, ProfileConfig] = Field(default_factory=dict)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    if not config_path:
        # Default search path: current working directory or relative
        candidate = Path("config.yaml")
        if candidate.exists():
            config_path = str(candidate)

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            config = AppConfig(**raw)
    else:
        config = AppConfig()

    # Environment variable overrides
    if "WRAPPER_PORT" in os.environ:
        config.server.port = int(os.environ["WRAPPER_PORT"])
    if "WRAPPER_HOST" in os.environ:
        config.server.host = os.environ["WRAPPER_HOST"]

    return config

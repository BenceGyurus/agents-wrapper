from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = True
    format: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    keep_alive: Optional[str] = None


class GenerateRequest(BaseModel):
    model: str
    prompt: str
    system: Optional[str] = None
    stream: bool = True
    format: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    keep_alive: Optional[str] = None


class ModelDetails(BaseModel):
    parent_model: str = ""
    format: str = "cli"
    family: str = "antigravity"
    families: List[str] = Field(default_factory=lambda: ["cli"])
    parameter_size: str = "agent"
    quantization_level: str = "none"


class ModelInfo(BaseModel):
    name: str
    model: str
    modified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    size: int = 0
    digest: str = "cli-agent-wrapper"
    details: ModelDetails = Field(default_factory=ModelDetails)


class TagsResponse(BaseModel):
    models: List[ModelInfo]


class VersionResponse(BaseModel):
    version: str = "0.5.1"


class ShowRequest(BaseModel):
    model: str


class ShowResponse(BaseModel):
    modelfile: str = "# Ollama CLI Wrapper Profile"
    parameters: str = "temperature 0.7"
    template: str = "{{ .System }}\n{{ .Prompt }}"
    details: ModelDetails = Field(default_factory=ModelDetails)
    modified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Response formats for Chat and Generate
class ChatMessageResponse(BaseModel):
    role: str = "assistant"
    content: str


class ChatStreamChunk(BaseModel):
    model: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    message: ChatMessageResponse
    done: bool = False
    done_reason: Optional[str] = None
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    eval_count: Optional[int] = None
    eval_duration: Optional[int] = None


class GenerateStreamChunk(BaseModel):
    model: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    response: str
    done: bool = False
    done_reason: Optional[str] = None
    total_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    eval_count: Optional[int] = None

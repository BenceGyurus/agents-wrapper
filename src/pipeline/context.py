from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from src.schemas.ollama import ChatMessage, ChatRequest, GenerateRequest


@dataclass
class PipelineContext:
    request: Union[ChatRequest, GenerateRequest]
    model: str
    prompt_text: str = ""
    system_prompt: Optional[str] = None
    messages: List[ChatMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Abort / Interception signals
    aborted: bool = False
    abort_reason: Optional[str] = None
    abort_status_code: int = 400
    
    # Injected extra context (e.g. from RAG or security notes)
    injected_context: List[str] = field(default_factory=list)

    # Multimodal image attachments
    raw_images: List[str] = field(default_factory=list)
    saved_image_paths: List[str] = field(default_factory=list)

    def abort(self, reason: str, status_code: int = 400) -> None:
        """Short-circuits the pipeline immediately."""
        self.aborted = True
        self.abort_reason = reason
        self.abort_status_code = status_code

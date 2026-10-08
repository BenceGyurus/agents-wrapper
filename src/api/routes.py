import json
import time
import logging
from datetime import datetime, timezone
from typing import AsyncIterator
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse

from src.schemas.ollama import (
    ChatRequest,
    ChatStreamChunk,
    ChatMessageResponse,
    GenerateRequest,
    GenerateStreamChunk,
    ShowRequest,
    ShowResponse,
    TagsResponse,
    VersionResponse,
)
from src.pipeline.context import PipelineContext
from src.pipeline.runner import PipelineRunner
from src.backends.router import ModelRouter
from src.backends.base import BackendExecutionError
from src.config import AppConfig

logger = logging.getLogger("wrapper.api")

router = APIRouter()


def create_routes(config: AppConfig, model_router: ModelRouter) -> APIRouter:
    
    @router.get("/", response_class=PlainTextResponse)
    async def root():
        """Basic liveness probe for Open WebUI and proxies."""
        return "Ollama is running"

    @router.get("/api/version", response_model=VersionResponse)
    async def get_version():
        """Version endpoint used by Open WebUI connection checks."""
        return VersionResponse(version="0.5.1")

    @router.get("/api/tags", response_model=TagsResponse)
    async def get_tags():
        """Lists available models (dynamically discovered and configured)."""
        models = await model_router.get_all_models()
        return TagsResponse(models=models)

    @router.post("/api/show", response_model=ShowResponse)
    async def show_model(req: ShowRequest):
        """Returns details for a requested model."""
        backend, kwargs, _ = model_router.resolve(req.model)
        return ShowResponse(
            modelfile=f"# Model profile: {req.model}\nFROM {backend.name}",
            parameters=f"backend={backend.name} options={kwargs}",
            template="{{ .System }}\n{{ .Prompt }}",
        )

    @router.post("/api/chat")
    async def chat(req: ChatRequest):
        """Main chat endpoint compatible with Ollama and Open WebUI."""
        backend, backend_kwargs, overrides = model_router.resolve(req.model)
        pipeline = PipelineRunner.from_config(config.pipeline, overrides)

        # Separate system message if provided
        system_content = None
        for m in req.messages:
            if m.role.lower() == "system":
                system_content = m.content
                break

        ctx = PipelineContext(
            request=req,
            model=req.model,
            system_prompt=system_content,
            messages=req.messages,
            metadata={"options": req.options or {}},
        )

        # 1. Run Pre-Execution Pipeline (Security, Sanitizer, External hooks)
        ctx = await pipeline.pre_process(ctx)

        # Handle Short-Circuit / Security Abort
        if ctx.aborted:
            logger.warning(f"Request blocked by security layer: {ctx.abort_reason}")
            if req.stream:
                async def security_block_stream():
                    err_payload = ChatStreamChunk(
                        model=req.model,
                        message=ChatMessageResponse(
                            role="assistant",
                            content=f"⚠️ **Request Blocked by Security Policy**\n\n{ctx.abort_reason}"
                        ),
                        done=True,
                        done_reason="security_violation",
                    )
                    yield json.dumps(err_payload.model_dump()) + "\n"

                return StreamingResponse(
                    security_block_stream(),
                    media_type="application/x-ndjson"
                )
            else:
                raise HTTPException(status_code=ctx.abort_status_code, detail=ctx.abort_reason)

        start_time_ns = time.time_ns()

        # 2. Execution & Streaming
        if req.stream:
            async def ndjson_generator() -> AsyncIterator[str]:
                accumulated_parts = []
                try:
                    async for chunk in backend.stream(ctx.prompt_text, **backend_kwargs):
                        # Chunk interceptor
                        processed_chunk = await pipeline.post_process_chunk(chunk, ctx)
                        accumulated_parts.append(processed_chunk)

                        stream_chunk = ChatStreamChunk(
                            model=req.model,
                            message=ChatMessageResponse(role="assistant", content=processed_chunk),
                            done=False,
                        )
                        yield json.dumps(stream_chunk.model_dump()) + "\n"

                    # Run Post-Execution Pipeline on full response
                    full_response = "".join(accumulated_parts)
                    await pipeline.post_process_full(full_response, ctx)

                    # Final termination chunk
                    total_duration = time.time_ns() - start_time_ns
                    final_chunk = ChatStreamChunk(
                        model=req.model,
                        message=ChatMessageResponse(role="assistant", content=""),
                        done=True,
                        done_reason="stop",
                        total_duration=total_duration,
                    )
                    yield json.dumps(final_chunk.model_dump()) + "\n"

                except BackendExecutionError as bee:
                    logger.error(f"Backend execution error: {bee}")
                    err_chunk = ChatStreamChunk(
                        model=req.model,
                        message=ChatMessageResponse(
                            role="assistant",
                            content=f"\n\n❌ **CLI Backend Execution Error**:\n```\n{str(bee)}\n```"
                        ),
                        done=True,
                        done_reason="error",
                    )
                    yield json.dumps(err_chunk.model_dump()) + "\n"
                except Exception as e:
                    logger.error(f"Unexpected streaming error: {e}", exc_info=True)
                    err_chunk = ChatStreamChunk(
                        model=req.model,
                        message=ChatMessageResponse(
                            role="assistant",
                            content=f"\n\n❌ **Internal Error**: {str(e)}"
                        ),
                        done=True,
                        done_reason="error",
                    )
                    yield json.dumps(err_chunk.model_dump()) + "\n"

            return StreamingResponse(ndjson_generator(), media_type="application/x-ndjson")

        else:
            # Non-streaming response
            try:
                full_raw = await backend.generate(ctx.prompt_text, **backend_kwargs)
                full_processed = await pipeline.post_process_full(full_raw, ctx)
                total_duration = time.time_ns() - start_time_ns

                return {
                    "model": req.model,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "message": {"role": "assistant", "content": full_processed},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": total_duration,
                }
            except BackendExecutionError as bee:
                raise HTTPException(status_code=502, detail=str(bee))

    @router.post("/api/generate")
    async def generate(req: GenerateRequest):
        """Raw prompt completion endpoint compatible with Ollama."""
        backend, backend_kwargs, overrides = model_router.resolve(req.model)
        pipeline = PipelineRunner.from_config(config.pipeline, overrides)

        ctx = PipelineContext(
            request=req,
            model=req.model,
            prompt_text=req.prompt,
            system_prompt=req.system,
            metadata={"options": req.options or {}},
        )

        ctx = await pipeline.pre_process(ctx)

        if ctx.aborted:
            if req.stream:
                async def security_block_stream():
                    err_payload = GenerateStreamChunk(
                        model=req.model,
                        response=f"⚠️ Request Blocked by Security Policy: {ctx.abort_reason}",
                        done=True,
                        done_reason="security_violation",
                    )
                    yield json.dumps(err_payload.model_dump()) + "\n"
                return StreamingResponse(security_block_stream(), media_type="application/x-ndjson")
            else:
                raise HTTPException(status_code=ctx.abort_status_code, detail=ctx.abort_reason)

        start_time_ns = time.time_ns()

        if req.stream:
            async def ndjson_generator() -> AsyncIterator[str]:
                accumulated = []
                try:
                    async for chunk in backend.stream(ctx.prompt_text, **backend_kwargs):
                        processed_chunk = await pipeline.post_process_chunk(chunk, ctx)
                        accumulated.append(processed_chunk)
                        stream_chunk = GenerateStreamChunk(
                            model=req.model,
                            response=processed_chunk,
                            done=False,
                        )
                        yield json.dumps(stream_chunk.model_dump()) + "\n"

                    full_response = "".join(accumulated)
                    await pipeline.post_process_full(full_response, ctx)

                    total_duration = time.time_ns() - start_time_ns
                    final_chunk = GenerateStreamChunk(
                        model=req.model,
                        response="",
                        done=True,
                        done_reason="stop",
                        total_duration=total_duration,
                    )
                    yield json.dumps(final_chunk.model_dump()) + "\n"

                except Exception as e:
                    logger.error(f"Generate error: {e}", exc_info=True)
                    err_chunk = GenerateStreamChunk(
                        model=req.model,
                        response=f"\n\n❌ Error: {str(e)}",
                        done=True,
                        done_reason="error",
                    )
                    yield json.dumps(err_chunk.model_dump()) + "\n"

            return StreamingResponse(ndjson_generator(), media_type="application/x-ndjson")
        else:
            full_raw = await backend.generate(ctx.prompt_text, **backend_kwargs)
            full_processed = await pipeline.post_process_full(full_raw, ctx)
            total_duration = time.time_ns() - start_time_ns
            return {
                "model": req.model,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "response": full_processed,
                "done": True,
                "done_reason": "stop",
                "total_duration": total_duration,
            }

    return router

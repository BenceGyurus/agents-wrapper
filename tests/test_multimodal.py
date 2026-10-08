import os
import json
import base64
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from src.pipeline.context import PipelineContext
from src.pipeline.layers.multimodal import MultimodalImageLayer
from src.schemas.ollama import ChatMessage, ChatRequest
from src.server import create_app
from src.config import load_config

# Valid 1x1 pixel PNG
VALID_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def make_ctx_with_images(images: list) -> PipelineContext:
    msg = ChatMessage(role="user", content="Analyze this image", images=images)
    req = ChatRequest(model="mock", messages=[msg], stream=False)
    return PipelineContext(
        request=req,
        model="mock",
        prompt_text="Analyze this image",
        messages=[msg],
    )


@pytest.mark.asyncio
async def test_multimodal_layer_valid_image(tmp_path):
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path)})
    ctx = make_ctx_with_images([VALID_PNG_B64])

    res = await layer.pre_process(ctx)

    assert res.aborted is False
    assert len(res.saved_image_paths) == 1
    saved_file = Path(res.saved_image_paths[0])
    assert saved_file.exists()
    assert saved_file.suffix == ".png"
    assert len(res.injected_context) > 0
    assert "Attached Image #1" in res.injected_context[0]
    assert saved_file.name in res.injected_context[0]


@pytest.mark.asyncio
async def test_multimodal_layer_invalid_base64(tmp_path):
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path)})
    ctx = make_ctx_with_images(["this_is_not_valid_base64!!!"])

    res = await layer.pre_process(ctx)

    assert res.aborted is True
    assert "Invalid base64" in res.abort_reason


@pytest.mark.asyncio
async def test_multimodal_layer_oversized_image(tmp_path):
    # Set limit to 0 MB to trigger size check
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path), "max_image_size_mb": 0})
    ctx = make_ctx_with_images([VALID_PNG_B64])

    res = await layer.pre_process(ctx)

    assert res.aborted is True
    assert "exceeds maximum allowed size" in res.abort_reason


@pytest.mark.asyncio
async def test_chat_api_with_image_attachment():
    config = load_config()
    app = create_app(config)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "mock",
            "messages": [
                {
                    "role": "user",
                    "content": "What is depicted in this screenshot?",
                    "images": [VALID_PNG_B64],
                }
            ],
            "stream": False,
        }
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["done"] is True
        assert "Mock response from" in data["message"]["content"]


@pytest.mark.asyncio
async def test_tags_includes_clip_family():
    config = load_config()
    app = create_app(config)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/tags")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify that models advertise 'clip' in families so Open WebUI shows image upload
        for model in data["models"]:
            assert "clip" in model["details"]["families"]

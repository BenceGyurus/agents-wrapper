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


@pytest.mark.asyncio
async def test_multimodal_layer_max_images_limit(tmp_path):
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path), "max_images_per_request": 2})
    # Provide 3 images when limit is 2
    ctx = make_ctx_with_images([VALID_PNG_B64, VALID_PNG_B64, VALID_PNG_B64])

    res = await layer.pre_process(ctx)
    assert res.aborted is True
    assert "Too many file attachments" in res.abort_reason


def test_multimodal_cleanup_ttl(tmp_path):
    import time
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path), "ttl_hours": 1})
    
    # Create an old file with mtime set to 2 hours ago
    old_file = tmp_path / "old_image.png"
    old_file.write_bytes(b"dummy image data")
    old_mtime = time.time() - 7200
    os.utime(old_file, (old_mtime, old_mtime))

    # Create a fresh file
    fresh_file = tmp_path / "fresh_image.png"
    fresh_file.write_bytes(b"fresh image data")

    # Run cleanup
    deleted = layer.cleanup_media_dir(force=True)
    assert deleted == 1
    assert not old_file.exists()
    assert fresh_file.exists()


def test_multimodal_cleanup_storage_cap(tmp_path):
    import time
    # Set cap to 100 KB
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path), "max_storage_mb": 0.0001, "ttl_hours": 100})
    
    # Create 3 files of 50KB each
    f1 = tmp_path / "img1.png"
    f1.write_bytes(b"x" * 50000)
    os.utime(f1, (time.time() - 100, time.time() - 100))

    f2 = tmp_path / "img2.png"
    f2.write_bytes(b"x" * 50000)
    os.utime(f2, (time.time() - 50, time.time() - 50))

    f3 = tmp_path / "img3.png"
    f3.write_bytes(b"x" * 50000)
    os.utime(f3, (time.time(), time.time()))

    # Total is 150KB > 100KB, should delete oldest
    deleted = layer.cleanup_media_dir(force=True)
    assert deleted >= 1
    assert not f1.exists()  # Oldest should be purged first


@pytest.mark.asyncio
async def test_multimodal_pdf_support(tmp_path):
    layer = MultimodalImageLayer(config={"media_dir": str(tmp_path)})
    # Minimal PDF base64 (%PDF-1.4 header)
    pdf_bytes = b"%PDF-1.4\n%EOF"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    ctx = make_ctx_with_images([pdf_b64])
    res = await layer.pre_process(ctx)

    assert res.aborted is False
    assert len(res.saved_image_paths) == 1
    saved_file = Path(res.saved_image_paths[0])
    assert saved_file.exists()
    assert saved_file.suffix == ".pdf"


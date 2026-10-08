import json
import pytest
from httpx import AsyncClient, ASGITransport
from src.server import create_app
from src.config import load_config


@pytest.mark.asyncio
async def test_live_agy_chat_stream():
    """Live integration test invoking real agy CLI through the Ollama wrapper."""
    config = load_config()
    app = create_app(config)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "agy",
            "messages": [
                {"role": "user", "content": "What is 2+2? Answer only with the number 4 and nothing else."}
            ],
            "stream": True,
        }
        resp = await client.post("/api/chat", json=payload, timeout=30.0)
        assert resp.status_code == 200

        lines = [line.strip() for line in resp.text.split("\n") if line.strip()]
        assert len(lines) >= 1

        chunks = [json.loads(line) for line in lines]
        combined = "".join(c["message"]["content"] for c in chunks)
        assert "4" in combined
        assert chunks[-1]["done"] is True

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import AppConfig, load_config
from src.backends.router import ModelRouter
from src.api.routes import create_routes


def setup_logging(level_name: str = "info"):
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_app(config: AppConfig = None) -> FastAPI:
    if config is None:
        config = load_config()

    setup_logging(config.server.log_level)
    logger = logging.getLogger("wrapper.server")

    model_router = ModelRouter(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Initializing CLI Agent Wrapper...")
        # Pre-cache available models
        discovered = await model_router.discover_agy_models()
        logger.info(f"Available Antigravity models discovered: {len(discovered)}")
        logger.info(f"Server ready on http://{config.server.host}:{config.server.port}")
        yield
        logger.info("Shutting down CLI Agent Wrapper...")

    app = FastAPI(
        title="Ollama-compatible CLI Agent Wrapper",
        description="Transparent Ollama gateway for Antigravity and Codex CLIs with pluggable security & RAG middleware.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Allow CORS so Open WebUI can connect from any origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach Ollama endpoints
    routes = create_routes(config, model_router)
    app.include_router(routes)

    return app


# Default app instance for 'uvicorn src.server:app'
app = create_app()

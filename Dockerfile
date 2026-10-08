# Debian 12 (Bookworm) based lightweight Python image
FROM python:3.12-slim-bookworm

LABEL maintainer="Bence Gyurus"
LABEL description="agents-wrapper: Ollama-compatible API for Antigravity & Codex CLIs"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=11434 \
    HOST=0.0.0.0

# Install minimal system dependencies for Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition first for caching
COPY requirements.txt pyproject.toml ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install build

# Copy source code and config
COPY config.yaml ./
COPY src/ ./src/
COPY README.md ./

# Install local package
RUN pip install --no-deps -e .

# Expose Ollama default port
EXPOSE 11434

# Healthcheck targeting Ollama liveness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:11434/api/version || exit 1

ENTRYPOINT ["agents-wrapper"]
CMD ["--host", "0.0.0.0", "--port", "11434"]

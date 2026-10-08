import argparse
import uvicorn
from src.config import load_config
from src.server import create_app


def main():
    parser = argparse.ArgumentParser(description="CLI Agent Wrapper for Ollama API")
    parser.add_argument("--host", type=str, default=None, help="Host address to bind (default from config: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default from config: 11434)")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

    app = create_app(config)

    print(f"Starting Ollama CLI Wrapper on http://{config.server.host}:{config.server.port} ...")
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()

import asyncio
import json
import logging
import shutil
from typing import Any, AsyncIterator, Dict
from src.backends.base import BaseBackend, BackendExecutionError

logger = logging.getLogger("wrapper.backend.codex")


class CodexBackend(BaseBackend):
    """Adapter for OpenAI Codex CLI ('codex')."""

    def __init__(self, name: str = "codex", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.binary_path = self.config.get("binary_path", "codex")
        self.default_sandbox = self.config.get("default_sandbox", "read-only")
        self.timeout_seconds = self.config.get("timeout_seconds", 120)

    def _resolve_binary(self) -> str:
        resolved = shutil.which(self.binary_path)
        if not resolved:
            if self.binary_path == "codex":
                for candidate in ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]:
                    if shutil.which(candidate):
                        return candidate
            raise BackendExecutionError(
                f"Codex CLI binary '{self.binary_path}' not found in PATH."
            )
        return resolved

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        binary = self._resolve_binary()
        sandbox = kwargs.get("sandbox") or self.default_sandbox

        cmd = [binary, "exec", prompt, "--json"]
        if sandbox:
            cmd.extend(["--sandbox", sandbox])

        cd_path = kwargs.get("cd")
        if cd_path:
            cmd.extend(["--cd", cd_path])

        logger.info(f"Executing Codex CLI: {' '.join(cmd[:3])} ... [prompt_len={len(prompt)}]")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            raise BackendExecutionError(f"Failed to spawn Codex CLI process: {e}")

        yielded_any = False
        stderr_output = []

        async def read_stderr():
            if proc.stderr:
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        stderr_output.append(decoded)

        stderr_task = asyncio.create_task(read_stderr())

        try:
            if proc.stdout:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break

                    decoded_line = line.decode("utf-8", errors="replace").strip()
                    if not decoded_line:
                        continue

                    try:
                        # Attempt to parse jsonl event
                        data = json.loads(decoded_line)
                        content = data.get("content") or data.get("text") or data.get("delta")
                        if content:
                            yielded_any = True
                            yield content
                    except json.JSONDecodeError:
                        yielded_any = True
                        yield decoded_line + "\n"

            await proc.wait()
            await stderr_task

            if proc.returncode != 0:
                err_msg = "\n".join(stderr_output) or f"Process exited with code {proc.returncode}"
                raise BackendExecutionError(f"Codex CLI execution failed:\n{err_msg}")

        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        except Exception as e:
            if not isinstance(e, BackendExecutionError):
                raise BackendExecutionError(str(e))
            raise

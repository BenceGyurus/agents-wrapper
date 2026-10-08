import asyncio
import json
import logging
import shutil
from typing import Any, AsyncIterator, Dict, Optional
from src.backends.base import BaseBackend, BackendExecutionError

logger = logging.getLogger("wrapper.backend.agy")


class AntigravityBackend(BaseBackend):
    """Adapter for Google Antigravity CLI ('agy')."""

    def __init__(self, name: str = "agy", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.binary_path = self.config.get("binary_path", "agy")
        self.default_model = self.config.get("default_model", "gemini-3.8-flash-high")
        self.default_effort = self.config.get("default_effort", "high")
        self.timeout_seconds = self.config.get("timeout_seconds", 120)

    def _resolve_binary(self) -> str:
        resolved = shutil.which(self.binary_path)
        if not resolved:
            # Check common locations only if using the default name
            if self.binary_path == "agy":
                for candidate in ["/opt/homebrew/bin/agy", "/usr/local/bin/agy"]:
                    if shutil.which(candidate):
                        return candidate
            raise BackendExecutionError(
                f"Antigravity CLI binary '{self.binary_path}' not found in PATH."
            )
        return resolved

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        binary = self._resolve_binary()
        
        # Build command flags
        cmd = [binary, "-p", prompt, "--output-format", "stream-json"]

        model = kwargs.get("model") or self.default_model
        if model:
            cmd.extend(["--model", model])

        mode = kwargs.get("mode")
        if mode:
            cmd.extend(["--mode", mode])

        effort = kwargs.get("effort") or self.default_effort
        if effort:
            cmd.extend(["--effort", effort])

        logger.info(f"Executing Antigravity CLI: {' '.join(cmd[:4])} ... [prompt_len={len(prompt)}]")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

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
                        data = json.loads(decoded_line)
                        event = data.get("event")

                        if event == "step_update":
                            step = data.get("step_update", {})
                            delta = step.get("text_delta")
                            if delta:
                                yielded_any = True
                                yield delta

                        elif event == "result":
                            result = data.get("result", {})
                            final_resp = result.get("response", "")
                            # If no deltas were yielded before, yield full final response
                            if not yielded_any and final_resp:
                                yielded_any = True
                                yield final_resp

                    except json.JSONDecodeError:
                        # Fallback for plain text or unexpected raw stdout line
                        yielded_any = True
                        yield decoded_line + "\n"

            await proc.wait()
            await stderr_task

            if proc.returncode != 0 and not yielded_any:
                err_msg = "\n".join(stderr_output) or f"Process exited with code {proc.returncode}"
                raise BackendExecutionError(f"Antigravity CLI failed: {err_msg}")

        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        except Exception as e:
            if not isinstance(e, BackendExecutionError):
                logger.error(f"Error during Antigravity execution: {e}")
                raise BackendExecutionError(str(e))
            raise

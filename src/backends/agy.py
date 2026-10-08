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
        self.default_effort = self.config.get("default_effort", "")
        self.skip_permissions = self.config.get("skip_permissions", True)
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
        cmd = [binary, "-p", prompt, "--output-format", "stream-json", "--disable-slash-commands"]

        if self.skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        model = kwargs.get("model") or self.default_model
        if model:
            cmd.extend(["--model", model])

        mode = kwargs.get("mode")
        if mode:
            cmd.extend(["--mode", mode])

        # Check if model name already specifies the reasoning effort level
        has_embedded_effort = False
        if model:
            for suffix in ["-low", "-medium", "-high", "-xhigh", "-max", "-thinking"]:
                if model.endswith(suffix):
                    has_embedded_effort = True
                    break

        # Only pass --effort if the model does not already dictate it
        if not has_embedded_effort:
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
                            error_msg = result.get("error", "")
                            status = result.get("status", "")
                            denied_actions = result.get("denied_actions", [])

                            if denied_actions and not yielded_any:
                                denied_str = ", ".join(d.get("display_name", str(d)) for d in denied_actions)
                                raise BackendExecutionError(
                                    f"Antigravity tool permission was auto-denied: {denied_str}. "
                                    "Please ensure skip_permissions is enabled."
                                )

                            if status == "ERROR" and error_msg and not yielded_any:
                                raise BackendExecutionError(f"Antigravity CLI failed: {error_msg}")

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

            if not yielded_any:
                err_msg = "\n".join(stderr_output) or f"Process exited with code {proc.returncode} without output."
                logger.error(f"Antigravity CLI yielded 0 chars (exit code {proc.returncode}). Stderr: {err_msg}")
                raise BackendExecutionError(f"Antigravity CLI failed to produce a response:\n{err_msg}")

        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        except Exception as e:
            if not isinstance(e, BackendExecutionError):
                logger.error(f"Error during Antigravity execution: {e}")
                raise BackendExecutionError(str(e))
            raise

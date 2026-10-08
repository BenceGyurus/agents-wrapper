import os
import re
import uuid
import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.pipeline.base import BaseLayer
from src.pipeline.context import PipelineContext

logger = logging.getLogger("wrapper.multimodal")


class MultimodalImageLayer(BaseLayer):
    """Processes base64 encoded images from Ollama requests, saves them safely,
    and instructs CLI agents to inspect them via their file-reading tools.
    """

    MAGIC_BYTES: List[Tuple[bytes, str]] = [
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xff\xd8\xff", "jpg"),
        (b"GIF87a", "gif"),
        (b"GIF89a", "gif"),
        (b"BM", "bmp"),
        (b"%PDF-", "pdf"),
    ]

    def __init__(self, name: str = "multimodal_image", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.media_dir = Path(self.config.get("media_dir", "/tmp/agents_wrapper_media"))
        self.max_size_mb = self.config.get("max_image_size_mb", 25)
        self.max_size_bytes = self.max_size_mb * 1024 * 1024
        self.max_images_per_request = self.config.get("max_images_per_request", 10)
        
        # Cleanup configuration
        self.ttl_seconds = self.config.get("ttl_hours", 2) * 3600
        self.max_storage_bytes = self.config.get("max_storage_mb", 500) * 1024 * 1024
        self._last_cleanup_time = 0.0
        self._cleanup_interval_seconds = 300.0  # Run cleanup at most once every 5 minutes

        try:
            self.media_dir.mkdir(parents=True, exist_ok=True)
            self.cleanup_media_dir()
        except Exception as e:
            logger.warning(f"Failed to create or clean media directory '{self.media_dir}': {e}")

    def cleanup_media_dir(self, force: bool = False) -> int:
        """Deletes files older than TTL and enforces max storage capacity (LRU).
        Returns the number of files deleted.
        """
        import time
        now = time.time()
        if not force and (now - self._last_cleanup_time < self._cleanup_interval_seconds):
            return 0

        self._last_cleanup_time = now
        deleted_count = 0

        if not self.media_dir.exists():
            return 0

        files = []
        total_size = 0

        # 1. TTL-based cleanup
        for entry in self.media_dir.iterdir():
            if not entry.is_file():
                continue
            try:
                stat = entry.stat()
                file_age = now - stat.st_mtime
                if file_age > self.ttl_seconds:
                    entry.unlink(missing_ok=True)
                    deleted_count += 1
                    logger.debug(f"TTL cleaned old attachment: {entry.name}")
                else:
                    files.append((stat.st_mtime, stat.st_size, entry))
                    total_size += stat.st_size
            except Exception as e:
                logger.warning(f"Error inspecting media file {entry}: {e}")

        # 2. Storage cap enforcement (purge oldest files if over limit)
        if total_size > self.max_storage_bytes:
            # Sort by mtime ascending (oldest first)
            files.sort(key=lambda x: x[0])
            target_size = int(self.max_storage_bytes * 0.75)  # reduce to 75% of limit

            for _, size, file_path in files:
                if total_size <= target_size:
                    break
                try:
                    file_path.unlink(missing_ok=True)
                    total_size -= size
                    deleted_count += 1
                    logger.info(f"Storage cap evicted media file: {file_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Media cleanup finished: removed {deleted_count} stale/overflow files.")
        return deleted_count

    def _detect_extension(self, data: bytes) -> str:
        """Determines image extension from binary header magic bytes."""
        for magic, ext in self.MAGIC_BYTES:
            if data.startswith(magic):
                return ext
        # Check WEBP: starts with RIFF and has WEBP at offset 8
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
        return "png"  # Default fallback

    def _extract_images_from_context(self, ctx: PipelineContext) -> List[str]:
        """Gathers all base64 images from request or messages."""
        collected = []

        # From GenerateRequest
        req_images = getattr(ctx.request, "images", None)
        if req_images and isinstance(req_images, list):
            collected.extend(req_images)

        # From ChatRequest messages
        for msg in ctx.messages:
            msg_images = getattr(msg, "images", None)
            if msg_images and isinstance(msg_images, list):
                collected.extend(msg_images)

        return collected

    async def pre_process(self, ctx: PipelineContext) -> PipelineContext:
        # Periodic cleanup of expired or overflow media files
        self.cleanup_media_dir()

        images_b64 = self._extract_images_from_context(ctx)
        if not images_b64:
            return ctx

        # Enforce maximum number of attachments per request
        if len(images_b64) > self.max_images_per_request:
            reason = (
                f"Too many file attachments: received {len(images_b64)}, "
                f"maximum allowed is {self.max_images_per_request}."
            )
            logger.warning(reason)
            ctx.abort(f"Security Alert: {reason}", status_code=400)
            return ctx

        ctx.raw_images.extend(images_b64)
        saved_paths: List[str] = []

        for idx, raw_b64 in enumerate(images_b64, start=1):
            # Clean data URI prefix if present (e.g. "data:image/png;base64,....")
            clean_b64 = re.sub(r"^data:image/[a-zA-Z]+;base64,", "", raw_b64.strip())

            try:
                raw_bytes = base64.b64decode(clean_b64, validate=True)
            except Exception as e:
                reason = f"Image #{idx} decoding failed: Invalid base64 data ({e})"
                logger.error(reason)
                ctx.abort(f"Security Alert: {reason}", status_code=400)
                return ctx

            # Validate size
            if len(raw_bytes) > self.max_size_bytes:
                reason = f"Image #{idx} exceeds maximum allowed size of {self.max_size_mb} MB"
                logger.warning(reason)
                ctx.abort(f"Security Alert: {reason}", status_code=400)
                return ctx

            ext = self._detect_extension(raw_bytes)
            file_name = f"img_{uuid.uuid4().hex[:12]}.{ext}"
            target_path = self.media_dir / file_name

            try:
                target_path.write_bytes(raw_bytes)
                saved_paths.append(str(target_path.resolve()))
                logger.info(f"Saved multimodal image attachment to: {target_path}")
            except Exception as e:
                logger.error(f"Failed to write image file: {e}")
                ctx.abort(f"Internal error saving image attachment: {e}", status_code=500)
                return ctx

        ctx.saved_image_paths.extend(saved_paths)

        # Inject instructions for the CLI agent to view and analyze the images
        attachment_notices = []
        for idx, img_path in enumerate(saved_paths, start=1):
            notice = (
                f"[Attached Image #{idx}: file://{img_path}]\n"
                f"The user has attached an image file located at: file://{img_path}\n"
                f"Please inspect and analyze this image (using your view_file tool if necessary) to answer the user's request."
            )
            attachment_notices.append(notice)

        combined_notice = "\n\n".join(attachment_notices)
        ctx.injected_context.insert(0, combined_notice)

        return ctx

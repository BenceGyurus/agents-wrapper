import asyncio
import time
import uuid
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from src.config import QueueConfig

logger = logging.getLogger("wrapper.queue")


class QueueFullError(Exception):
    """Raised when the worker queue reaches maximum capacity."""
    pass


class QueueTimeoutError(Exception):
    """Raised when a request waits too long in the queue for an available worker."""
    pass


class JobTimeoutError(Exception):
    """Raised when a model execution takes longer than allowed by timeout."""
    pass


class WorkerJob:
    def __init__(self, job_id: str, model: str):
        self.job_id = job_id
        self.model = model
        self.started_at = time.time()


class WorkerQueueManager:
    """Manages worker concurrency, queuing, execution timeouts, and process tracking."""

    def __init__(self, config: QueueConfig):
        self.config = config
        self.enabled = config.enabled
        self.max_workers = config.max_workers
        self.max_queue_size = config.max_queue_size
        self.job_timeout = config.job_timeout_seconds
        self.queue_wait_timeout = config.queue_wait_timeout_seconds

        self._semaphore = asyncio.Semaphore(self.max_workers)
        self._waiting_count = 0
        self._active_jobs: Dict[str, WorkerJob] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_jobs)

    @property
    def waiting_count(self) -> int:
        return self._waiting_count

    def get_active_models(self) -> List[Dict[str, Any]]:
        """Returns currently running models for the Ollama /api/ps endpoint."""
        now = time.time()
        active = []
        for job_id, job in list(self._active_jobs.items()):
            active.append({
                "name": job.model,
                "model": job.model,
                "size": 0,
                "digest": f"active-{job.model}",
                "details": {
                    "format": "cli",
                    "family": "antigravity",
                },
                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + self.job_timeout)),
                "size_vram": 0,
            })
        return active

    async def run_streaming(
        self,
        model: str,
        generator_func: Callable[[], AsyncIterator[str]],
    ) -> AsyncIterator[str]:
        """Runs a streaming task through the worker queue with wait & execution timeouts."""
        if not self.enabled:
            async for chunk in generator_func():
                yield chunk
            return

        # 1. Capacity check
        async with self._lock:
            total_in_flight = self.active_count + self._waiting_count
            if total_in_flight >= (self.max_workers + self.max_queue_size):
                reason = f"Server is busy: queue capacity reached ({total_in_flight} active/waiting)."
                logger.warning(reason)
                raise QueueFullError(reason)

            self._waiting_count += 1

        # 2. Wait for an available worker
        job_id = uuid.uuid4().hex[:8]
        acquired = False
        try:
            logger.info(
                f"[QUEUE] Request {job_id} for model='{model}' queued. "
                f"(active={self.active_count}/{self.max_workers}, waiting={self._waiting_count})"
            )
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.queue_wait_timeout)
            acquired = True
        except asyncio.TimeoutError:
            reason = f"Timed out after {self.queue_wait_timeout}s waiting for a free worker slot."
            logger.warning(f"[QUEUE] {reason} (job_id={job_id})")
            raise QueueTimeoutError(reason)
        finally:
            async with self._lock:
                self._waiting_count = max(0, self._waiting_count - 1)

        # 3. Worker slot acquired: register and execute with timeout
        job = WorkerJob(job_id=job_id, model=model)
        self._active_jobs[job_id] = job
        logger.info(
            f"[WORKER] Worker slot assigned to job {job_id} (model='{model}'). "
            f"(active={self.active_count}/{self.max_workers})"
        )

        try:
            deadline = time.time() + self.job_timeout
            gen = generator_func()

            while True:
                time_remaining = deadline - time.time()
                if time_remaining <= 0:
                    raise JobTimeoutError(f"Model execution timed out after {self.job_timeout}s.")

                try:
                    # Fetch next item from async generator with remaining timeout
                    chunk = await asyncio.wait_for(gen.__anext__(), timeout=time_remaining)
                    yield chunk
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise JobTimeoutError(f"Model execution timed out after {self.job_timeout}s.")

        finally:
            self._active_jobs.pop(job_id, None)
            if acquired:
                self._semaphore.release()
            duration = round(time.time() - job.started_at, 2)
            logger.info(f"[WORKER] Released worker slot for job {job_id} after {duration}s.")

    async def run_task(
        self,
        model: str,
        coroutine_func: Callable[[], Any],
    ) -> Any:
        """Runs a non-streaming coroutine through the worker queue with wait & execution timeouts."""
        if not self.enabled:
            return await coroutine_func()

        async with self._lock:
            total_in_flight = self.active_count + self._waiting_count
            if total_in_flight >= (self.max_workers + self.max_queue_size):
                reason = f"Server is busy: queue capacity reached ({total_in_flight} active/waiting)."
                logger.warning(reason)
                raise QueueFullError(reason)
            self._waiting_count += 1

        job_id = uuid.uuid4().hex[:8]
        acquired = False
        try:
            logger.info(
                f"[QUEUE] Task {job_id} for model='{model}' queued. "
                f"(active={self.active_count}/{self.max_workers}, waiting={self._waiting_count})"
            )
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.queue_wait_timeout)
            acquired = True
        except asyncio.TimeoutError:
            reason = f"Timed out after {self.queue_wait_timeout}s waiting for a free worker slot."
            logger.warning(f"[QUEUE] {reason} (job_id={job_id})")
            raise QueueTimeoutError(reason)
        finally:
            async with self._lock:
                self._waiting_count = max(0, self._waiting_count - 1)

        job = WorkerJob(job_id=job_id, model=model)
        self._active_jobs[job_id] = job
        logger.info(f"[WORKER] Worker slot assigned to non-streaming task {job_id} (model='{model}').")

        try:
            return await asyncio.wait_for(coroutine_func(), timeout=self.job_timeout)
        except asyncio.TimeoutError:
            raise JobTimeoutError(f"Model execution timed out after {self.job_timeout}s.")
        finally:
            self._active_jobs.pop(job_id, None)
            if acquired:
                self._semaphore.release()
            duration = round(time.time() - job.started_at, 2)
            logger.info(f"[WORKER] Released worker slot for task {job_id} after {duration}s.")

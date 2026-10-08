import asyncio
import pytest
from src.task_queue.manager import (
    WorkerQueueManager,
    QueueFullError,
    QueueTimeoutError,
    JobTimeoutError,
)
from src.config import QueueConfig


@pytest.mark.asyncio
async def test_queue_concurrency_limit():
    config = QueueConfig(
        enabled=True,
        max_workers=2,
        max_queue_size=1,
        job_timeout_seconds=5,
        queue_wait_timeout_seconds=1,
    )
    qm = WorkerQueueManager(config)

    active_tasks = 0
    max_observed_active = 0

    async def sample_job():
        nonlocal active_tasks, max_observed_active
        active_tasks += 1
        max_observed_active = max(max_observed_active, active_tasks)
        await asyncio.sleep(0.1)
        active_tasks -= 1
        return "done"

    results = await asyncio.gather(
        qm.run_task("test-model", sample_job),
        qm.run_task("test-model", sample_job),
        qm.run_task("test-model", sample_job),
    )

    assert results == ["done", "done", "done"]
    # Max active concurrent jobs should never exceed max_workers (2)
    assert max_observed_active <= 2


@pytest.mark.asyncio
async def test_queue_job_timeout():
    config = QueueConfig(
        enabled=True,
        max_workers=1,
        max_queue_size=5,
        job_timeout_seconds=0.1,  # Short timeout
        queue_wait_timeout_seconds=2,
    )
    qm = WorkerQueueManager(config)

    async def long_running_job():
        await asyncio.sleep(1.0)
        return "should not reach"

    with pytest.raises(JobTimeoutError) as exc_info:
        await qm.run_task("slow-model", long_running_job)

    assert "timed out after" in str(exc_info.value)
    # Ensure worker slot was properly released
    assert qm.active_count == 0


@pytest.mark.asyncio
async def test_queue_wait_timeout():
    config = QueueConfig(
        enabled=True,
        max_workers=1,
        max_queue_size=5,
        job_timeout_seconds=10,
        queue_wait_timeout_seconds=0.1,  # Very short wait timeout
    )
    qm = WorkerQueueManager(config)

    async def slow_holder():
        await asyncio.sleep(0.5)

    # First task occupies the only worker slot
    t1 = asyncio.create_task(qm.run_task("m1", slow_holder))
    await asyncio.sleep(0.02)

    # Second task tries to queue, should time out waiting for slot
    with pytest.raises(QueueTimeoutError) as exc_info:
        await qm.run_task("m2", lambda: asyncio.sleep(0.01))

    assert "waiting for a free worker slot" in str(exc_info.value)
    await t1


@pytest.mark.asyncio
async def test_active_models_for_ps():
    config = QueueConfig(enabled=True, max_workers=2)
    qm = WorkerQueueManager(config)

    assert qm.get_active_models() == []

    started_event = asyncio.Event()

    async def held_task():
        started_event.set()
        await asyncio.sleep(0.2)
        return "ok"

    t = asyncio.create_task(qm.run_task("agy:gemini-3.8-flash", held_task))
    await started_event.wait()

    active = qm.get_active_models()
    assert len(active) == 1
    assert active[0]["model"] == "agy:gemini-3.8-flash"

    await t
    assert qm.get_active_models() == []

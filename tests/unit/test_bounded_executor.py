import threading

import pytest

from app.integrations.bounded_executor import BoundedExecutor


def test_executor_rejects_work_when_worker_and_queue_are_full():
    executor = BoundedExecutor(max_workers=1, max_pending=1, thread_name_prefix="test-bounded")
    release = threading.Event()
    try:
        running = executor.submit(release.wait)
        queued = executor.submit(lambda: "queued")
        rejected = executor.submit(lambda: "rejected")

        assert running is not None
        assert queued is not None
        assert rejected is None
        release.set()
        assert queued.result(timeout=2) == "queued"
    finally:
        release.set()
        executor.shutdown()


def test_executor_releases_capacity_after_job_completion():
    executor = BoundedExecutor(max_workers=1, max_pending=0, thread_name_prefix="test-release")
    try:
        first = executor.submit(lambda: 1)
        assert first is not None
        assert first.result(timeout=2) == 1
        second = executor.submit(lambda: 2)
        assert second is not None
        assert second.result(timeout=2) == 2
    finally:
        executor.shutdown()


@pytest.mark.parametrize(
    ("max_workers", "max_pending"),
    [(0, 0), (1, -1)],
)
def test_executor_rejects_invalid_capacity(max_workers, max_pending):
    with pytest.raises(ValueError):
        BoundedExecutor(
            max_workers=max_workers,
            max_pending=max_pending,
            thread_name_prefix="invalid",
        )

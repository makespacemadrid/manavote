"""Small bounded wrapper around :mod:`concurrent.futures` executors."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable


class BoundedExecutor:
    """Reject jobs instead of allowing an unbounded in-memory work queue."""

    def __init__(self, *, max_workers: int, max_pending: int, thread_name_prefix: str):
        if max_workers < 1 or max_pending < 0:
            raise ValueError("max_workers must be positive and max_pending cannot be negative")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._capacity = threading.BoundedSemaphore(max_workers + max_pending)

    def submit(self, function: Callable, *args, **kwargs) -> Future | None:
        """Submit immediately, or return ``None`` when all slots are occupied."""
        if not self._capacity.acquire(blocking=False):
            return None
        try:
            future = self._executor.submit(function, *args, **kwargs)
        except RuntimeError:
            self._capacity.release()
            raise
        future.add_done_callback(lambda _future: self._capacity.release())
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

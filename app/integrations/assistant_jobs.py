"""Owned process-local futures and bounded, content-free assistant telemetry."""
from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from app.integrations.assistant_safety import localized

CANCELLED_MESSAGE = "Queued assistant request cancelled."
RUNNING_MESSAGE = "Your request is starting or already running. It may still complete; completed actions cannot be undone."
MISSING_MESSAGE = "No queued request could be cancelled. A running request may still reply."
PENDING_MESSAGE = "✅ Pending action cancelled."


@dataclass(eq=False)
class AssistantJob:
    owner: tuple[int, int, int]
    enqueued_at: float = field(default_factory=time.monotonic)
    state: str = "queued"
    future: object = None
    failure_reason: str | None = None
    rejected: bool = False


class AssistantJobs:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = set()
        self._counts = Counter({name: 0 for name in ('completed','failed','cancelled','rejected')})
        self._reasons = Counter()
        self._latencies = {stage: {'count': 0, 'total_ms': 0.0, 'max_ms': 0.0} for stage in ('queue','model','mcp','delivery')}
        self._stage_failures = Counter({stage: 0 for stage in ('model','mcp','delivery')})

    def create(self, member_id, chat_id, telegram_user_id):
        job = AssistantJob((int(member_id), int(chat_id), int(telegram_user_id)))
        with self._lock:
            self._jobs.add(job)
        return job

    def start(self, job):
        with self._lock:
            if job in self._jobs:
                job.state = 'running'
        self.observe('queue', (time.monotonic() - job.enqueued_at) * 1000)

    def attach(self, job, future):
        with self._lock:
            if job in self._jobs:
                job.future = future

    def reject(self, reason):
        with self._lock:
            self._counts['rejected'] += 1
            self._reasons[reason] += 1

    def finish(self, job, outcome='completed', reason='completed'):
        with self._lock:
            if job not in self._jobs:
                return
            self._jobs.remove(job)
            job.state = 'terminal'
            if outcome == 'completed' and job.failure_reason:
                outcome, reason = ('rejected' if job.rejected else 'failed'), job.failure_reason
            self._counts[outcome] += 1
            self._reasons[reason] += 1

    def observe(self, stage, milliseconds):
        value = max(0, float(milliseconds))
        with self._lock:
            summary = self._latencies[stage]
            summary['count'] += 1
            summary['total_ms'] += value
            summary['max_ms'] = max(summary['max_ms'], value)

    def event(self, job, event, details):
        if event in ('model_request_completed','model_request_failed'):
            self.observe('model', details['model_latency_ms'])
        if event in ('tool_request_completed','tool_request_failed'):
            self.observe('mcp', details['mcp_latency_ms'])
        stage = 'model' if event == 'model_request_failed' else 'mcp' if event == 'tool_request_failed' else None
        with self._lock:
            if stage:
                self._stage_failures[stage] += 1
                job.failure_reason = f'{stage}_failed'
            elif event == 'safety_rejected':
                job.failure_reason = details['reason_code']
                job.rejected = True
            elif event == 'reply_generation_failed':
                job.failure_reason = job.failure_reason or 'reply_generation_failed'

    def delivery_failed(self):
        with self._lock:
            self._stage_failures['delivery'] += 1

    def cancel(self, member_id, chat_id, telegram_user_id):
        owner = (int(member_id), int(chat_id), int(telegram_user_id))
        with self._lock:
            jobs = [(job, job.future) for job in self._jobs if job.owner == owner]
        cancelled = running = 0
        # Never hold the registry lock while Future.cancel invokes callbacks.
        for job, future in jobs:
            if future is None:
                running += 1  # Submission is in progress; no false cancellation claim.
            elif hasattr(future, 'cancel') and future.cancel():
                cancelled += 1
            elif not hasattr(future, 'done') or not future.done():
                running += 1
        return cancelled, running

    def snapshot(self):
        with self._lock:
            latencies = {name: {'count': values['count'], 'mean_ms': round(values['total_ms'] / values['count'], 2) if values['count'] else 0,
                                'max_ms': round(values['max_ms'], 2)} for name, values in self._latencies.items()}
            return {'scope': 'process', 'reset': 'process_restart',
                    'queued': sum(job.state == 'queued' for job in self._jobs),
                    'active': sum(job.state == 'running' for job in self._jobs),
                    'terminal': dict(self._counts), 'reasons': dict(self._reasons),
                    'stage_failures': dict(self._stage_failures), 'latency_ms': latencies}


def cancellation_response(cancelled, running, pending, language_code=None):
    parts = []
    if cancelled:
        parts.append(localized(CANCELLED_MESSAGE, language_code))
    if pending:
        parts.append(localized(PENDING_MESSAGE, language_code))
    if running:
        parts.append(localized(RUNNING_MESSAGE, language_code))
    if not parts:
        parts.append(localized(MISSING_MESSAGE, language_code))
    return '\n'.join(parts)

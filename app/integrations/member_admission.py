"""Process-local admission for queued and running assistant work per linked member."""
from __future__ import annotations

import threading

from translations import TRANSLATIONS

CONFIG_KEY = 'TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER'
MEMBER_BUSY_MESSAGE = '⏳ You already have an assistant request in progress. Wait for its reply, then try again.'
QUEUE_BUSY_MESSAGE = '⏳ The assistant is busy right now. Please try again shortly.'


def parse_member_job_limit(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f'{CONFIG_KEY} must be a positive integer')
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{CONFIG_KEY} must be a positive integer') from None
    if limit < 1:
        raise ValueError(f'{CONFIG_KEY} must be a positive integer')
    return limit


def busy_response(language_code, *, member_busy=False):
    language = str(language_code or 'en').lower().split('-', 1)[0].split('_', 1)[0]
    message = MEMBER_BUSY_MESSAGE if member_busy else QUEUE_BUSY_MESSAGE
    return TRANSLATIONS.get(language, TRANSLATIONS['en']).get(message, message)


class MemberAdmission:
    def __init__(self, max_outstanding_per_member=1):
        self.limit = parse_member_job_limit(max_outstanding_per_member)
        self._lock = threading.Lock()
        self._outstanding = {}

    def try_acquire(self, member_id):
        with self._lock:
            count = self._outstanding.get(member_id, 0)
            if count >= self.limit:
                return None
            self._outstanding[member_id] = count + 1
            return AdmissionLease(self, member_id)


class AdmissionLease:
    """Release exactly once, including inline execution and queued cancellation."""
    def __init__(self, admission, member_id):
        self._admission = admission
        self._member_id = member_id
        self._released = False

    def release(self):
        with self._admission._lock:
            if self._released:
                return
            self._released = True
            count = self._admission._outstanding[self._member_id] - 1
            if count:
                self._admission._outstanding[self._member_id] = count
            else:
                del self._admission._outstanding[self._member_id]

    def submit(self, executor, function, *args, **kwargs):
        def run():
            try:
                return function(*args, **kwargs)
            finally:
                self.release()
        try:
            future = executor.submit(run)
        except BaseException:
            self.release()
            raise
        if future is None:
            self.release()
        elif hasattr(future, 'add_done_callback'):
            # A cancelled queued job never invokes run(). Idempotence also handles
            # jobs that finished before callback registration and inline test executors.
            future.add_done_callback(lambda _future: self.release())
        return future

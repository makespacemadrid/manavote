import threading
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from app.integrations.bounded_executor import BoundedExecutor
from app.integrations.member_admission import MemberAdmission, busy_response, parse_member_job_limit


@pytest.mark.parametrize('value', [0, -1, '', 'bad', '1.5', None, True, 2.5])
def test_limit_requires_positive_integer(value):
    with pytest.raises(ValueError, match='TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER must be a positive integer'):
        parse_member_job_limit(value)


@pytest.mark.parametrize('value,expected', [('1', 1), (' 2 ', 2), (3, 3)])
def test_limit_parses_positive_integer(value, expected):
    assert parse_member_job_limit(value) == expected


def test_admission_is_atomic_across_concurrent_requests_for_one_member():
    admission = MemberAdmission(2)
    barrier = threading.Barrier(12)
    def acquire():
        barrier.wait(timeout=5)
        return admission.try_acquire(1)
    with ThreadPoolExecutor(max_workers=12) as executor:
        leases = list(executor.map(lambda _: acquire(), range(12)))
    accepted = [lease for lease in leases if lease is not None]
    assert len(accepted) == 2
    other = admission.try_acquire(2)
    assert other is not None
    for lease in [*accepted, other]:
        lease.release()
        lease.release()
    assert admission._outstanding == {}


def test_completion_failure_and_queued_cancellation_make_admission_reusable():
    admission = MemberAdmission()
    executor = BoundedExecutor(max_workers=1, max_pending=1, thread_name_prefix='member-admission-test')
    started, release = threading.Event(), threading.Event()
    try:
        def hold():
            started.set()
            release.wait(timeout=5)
        running = admission.try_acquire(1).submit(executor, hold)
        assert started.wait(timeout=2)
        assert not running.cancel()
        assert admission.try_acquire(1) is None
        queued = admission.try_acquire(2).submit(executor, lambda: 'queued')
        assert admission.try_acquire(2) is None
        assert queued.cancel()
        lease = admission.try_acquire(2)
        assert lease is not None
        lease.release()
        release.set()
        running.result(timeout=2)
        def fail():
            raise ValueError('worker failed')
        failed = admission.try_acquire(1).submit(executor, fail)
        with pytest.raises(ValueError, match='worker failed'):
            failed.result(timeout=2)
        lease = admission.try_acquire(1)
        assert lease is not None
        lease.release()
        assert admission._outstanding == {}
    finally:
        release.set()
        executor.shutdown()


@pytest.mark.parametrize('error', [RuntimeError('shutdown'), ValueError('submit failed')])
def test_submission_errors_release_member_and_global_capacity(error):
    admission = MemberAdmission()
    executor = BoundedExecutor(max_workers=1, max_pending=0, thread_name_prefix='submit-error-test')
    submit = executor._executor.submit
    try:
        executor._executor.submit = Mock(side_effect=error)
        with pytest.raises(type(error), match=str(error)):
            admission.try_acquire(1).submit(executor, lambda: None)
        executor._executor.submit = submit
        lease = admission.try_acquire(1)
        assert lease is not None
        future = lease.submit(executor, lambda: 42)
        assert future is not None and future.result(timeout=2) == 42
        assert admission._outstanding == {}
    finally:
        executor._executor.submit = submit
        executor.shutdown()


def test_queue_full_release_is_idempotent_and_does_not_release_another_lease():
    admission = MemberAdmission()
    lease = admission.try_acquire(1)
    assert lease.submit(Mock(submit=Mock(return_value=None)), lambda: None) is None
    newer = admission.try_acquire(1)
    assert newer is not None
    lease.release()
    assert admission.try_acquire(1) is None
    newer.release()
    assert admission._outstanding == {}


def test_inline_completion_and_future_callback_release_exactly_once():
    admission = MemberAdmission()
    class InlineExecutor:
        def submit(self, function):
            future = Future()
            future.set_result(function())
            return future
    future = admission.try_acquire(1).submit(InlineExecutor(), lambda: 'done')
    assert future.result() == 'done'
    assert admission._outstanding == {}


@pytest.mark.parametrize('language', ['es', 'es-ES', 'es_MX'])
def test_busy_responses_localize_spanish(language):
    assert 'Ya tienes' in busy_response(language, member_busy=True)
    assert 'ocupado' in busy_response(language)


def test_unknown_language_falls_back_to_english():
    assert 'already have' in busy_response('unknown', member_busy=True)
    assert 'busy right now' in busy_response(None)


def test_startup_rejects_invalid_member_limit(tmp_path):
    import os
    import subprocess
    import sys
    environment = os.environ.copy()
    environment.update(FLASK_ENV='test', SECRET_KEY='test-secret', APP_DB_PATH=str(tmp_path / 'startup.db'),
        TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER='0')
    result = subprocess.run([sys.executable, '-c', 'import app'], env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'TELEGRAM_AGENT_MAX_JOBS_PER_MEMBER must be a positive integer' in result.stderr

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from app.integrations.assistant_jobs import AssistantJobs, cancellation_response
from app.integrations.bounded_executor import BoundedExecutor
from app.integrations.member_admission import MemberAdmission
from app.services.assistant_health_service import build_assistant_health
from app.integrations import telegram_agent


def test_owned_cancellation_and_callback_idempotence():
    jobs = AssistantJobs()
    own = jobs.create(1,10,20)
    other = jobs.create(2,10,21)
    future = Future()
    jobs.attach(own,future)
    future.add_done_callback(lambda f: jobs.finish(own,'cancelled','worker_cancelled'))
    assert jobs.cancel(2,10,20) == (0,0)
    assert jobs.cancel(1,11,20) == (0,0)
    assert not future.cancelled()
    assert jobs.cancel(1,10,20) == (1,0)
    assert jobs.cancel(1,10,20) == (0,0)
    jobs.finish(own,'cancelled','worker_cancelled')
    snapshot = jobs.snapshot()
    assert snapshot['queued'] == 1 and snapshot['terminal']['cancelled'] == 1
    jobs.finish(other)
    assert jobs.snapshot()['queued'] == jobs.snapshot()['active'] == 0


def test_completion_before_attachment_does_not_leave_registry_entry():
    jobs=AssistantJobs()
    job=jobs.create(1,2,3)
    jobs.start(job)
    jobs.finish(job)
    jobs.attach(job,Future())
    jobs.finish(job)
    assert jobs.snapshot()['terminal']['completed'] == 1
    assert jobs.cancel(1,2,3) == (0,0)


def test_starting_and_running_jobs_are_not_claimed_cancelled():
    jobs=AssistantJobs()
    job=jobs.create(1,2,3)
    assert jobs.cancel(1,2,3) == (0,1)
    future=Future()
    future.set_running_or_notify_cancel()
    jobs.attach(job,future)
    jobs.start(job)
    assert jobs.cancel(1,2,3) == (0,1)
    assert jobs.snapshot()['active'] == 1
    future.set_result(None)
    jobs.finish(job)
    assert jobs.cancel(1,2,3) == (0,0)


def test_start_cancel_race_releases_member_and_global_capacity():
    executor=BoundedExecutor(max_workers=1,max_pending=1,thread_name_prefix='race-test')
    admission=MemberAdmission()
    jobs=AssistantJobs()
    block=threading.Event()
    started=threading.Event()
    worker=executor.submit(lambda:(started.set(),block.wait(5)))
    assert started.wait(5)
    ran=[]
    job=jobs.create(1,2,3)
    lease=admission.try_acquire(1)
    future=lease.submit(executor,lambda:(jobs.start(job),ran.append(1),jobs.finish(job)))
    jobs.attach(job,future)
    future.add_done_callback(lambda f: jobs.finish(job,'cancelled','worker_cancelled') if f.cancelled() else None)
    gate=threading.Barrier(2)
    def cancel():
        gate.wait(timeout=5)
        return jobs.cancel(1,2,3)
    def release():
        gate.wait(timeout=5)
        block.set()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cancellation=pool.submit(cancel)
            release_task=pool.submit(release)
            cancellation.result(timeout=5)
            release_task.result(timeout=5)
        worker.result(timeout=5)
        if not future.cancelled():
            future.result(timeout=5)
        snapshot=jobs.snapshot()
        assert snapshot['active'] == snapshot['queued'] == 0
        assert snapshot['terminal']['cancelled'] + snapshot['terminal']['completed'] == 1
        assert len(ran) == (0 if future.cancelled() else 1)
        reusable=admission.try_acquire(1)
        assert reusable is not None
        reusable.release()
        followup=executor.submit(lambda:'ok')
        assert followup is not None and followup.result(timeout=5) == 'ok'
    finally:
        block.set()
        executor.shutdown()


def test_latencies_and_failures_are_safe_bounded_aggregates(monkeypatch):
    jobs=AssistantJobs()
    job=jobs.create(1,2,3)
    jobs.start(job)
    jobs.event(job,'model_request_completed',{'model_latency_ms':10})
    jobs.event(job,'tool_request_failed',{'mcp_latency_ms':5})
    jobs.event(job,'model_request_failed',{'model_latency_ms':30})
    jobs.observe('delivery',4)
    jobs.delivery_failed()
    jobs.finish(job)
    jobs.finish(job)
    monkeypatch.setenv('OCABRA_API_KEY','private-health-value')
    monkeypatch.setenv('OCABRA_MODEL','private-health-value')
    monkeypatch.setenv('OCABRA_CHAT_URL','https://user:password@provider.example/chat?token=private')
    executor=type('Executor',(),{'max_workers':4,'max_pending':32})()
    health=build_assistant_health(jobs,executor,MemberAdmission(),configured=True)
    assert health['terminal']['failed'] == 1
    assert health['stage_failures'] == {'model':1,'mcp':1,'delivery':1}
    assert health['latency_ms']['model'] == {'count':2,'mean_ms':20.0,'max_ms':30.0}
    for private in ('private-health-value','provider.example','password','actor_member_id','telegram_user_id'):
        assert private not in json.dumps(health)


@pytest.mark.parametrize('timeout', ['bad','NaN','inf','0','-1'])
def test_health_reports_invalid_timeout_without_exposing_value(monkeypatch, timeout):
    monkeypatch.setenv('OCABRA_TIMEOUT_SECONDS',timeout)
    executor=type('Executor',(),{})()
    health=build_assistant_health(AssistantJobs(),executor,MemberAdmission(),configured=True)
    assert health['status'] == 'misconfigured'
    assert health['configuration']['timeout_seconds'] is None


def test_budget_rejection_is_terminal_rejection_and_response_localized():
    jobs=AssistantJobs()
    job=jobs.create(1,2,3)
    jobs.event(job,'safety_rejected',{'reason_code':'input_budget_exceeded'})
    jobs.finish(job)
    jobs.finish(job)
    assert jobs.snapshot()['terminal']['rejected'] == 1
    assert 'cancelada' in cancellation_response(1,0,True,'es-ES')
    assert 'completarse' in cancellation_response(0,1,False,'es')


def test_pending_cancellation_is_atomically_bound_to_member(tmp_path):
    import sqlite3
    path=tmp_path/'pending.db'
    def connect():
        conn=sqlite3.connect(path)
        conn.row_factory=sqlite3.Row
        return conn
    conn=connect()
    conn.execute('CREATE TABLE telegram_pending_actions(chat_id INTEGER, telegram_user_id INTEGER, tool_name TEXT, arguments_json TEXT, actor_member_id INTEGER, created_at REAL, schema_fingerprint TEXT, arguments_digest TEXT, PRIMARY KEY(chat_id,telegram_user_id))')
    conn.close()
    telegram_agent.configure_pending_action_store(connect)
    try:
        action=telegram_agent.PendingAction('create_poll',{},actor_member_id=1)
        telegram_agent._put_pending((10,20),action)
        assert not telegram_agent.cancel_pending_action(10,20,2)
        assert telegram_agent._get_pending((10,20)) == action
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:telegram_agent.cancel_pending_action(10,20,1),range(2)))
        assert results.count(True) == 1
        assert telegram_agent._get_pending((10,20)) is None
    finally:
        telegram_agent.configure_pending_action_store(None)

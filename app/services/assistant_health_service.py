"""Content-free operator health read model, without Flask dependencies."""
import math
import os
import re

from app.integrations.assistant_safety import ModelLimits, scrub


def build_assistant_health(jobs, executor, admission, *, configured):
    snapshot = jobs.snapshot()
    model = os.getenv('OCABRA_MODEL', 'ocabra')
    safe_model = scrub(model)
    if not re.fullmatch(r'[\w./:-]{1,128}', safe_model):
        safe_model = '[REDACTED]'
    try:
        timeout = float(os.getenv('OCABRA_TIMEOUT_SECONDS', '60'))
        if not math.isfinite(timeout) or timeout <= 0:
            timeout = None
    except ValueError:
        timeout = None
    workers = getattr(executor, 'max_workers', 4)
    pending = getattr(executor, 'max_pending', 32)
    limits = ModelLimits.from_env()
    snapshot['configuration'] = {'enabled': bool(configured), 'model': safe_model,
        'timeout_seconds': timeout, 'workers': workers, 'max_pending': pending,
        'max_jobs_per_member': admission.limit, 'context_budget': limits.context,
        'input_budget': limits.input, 'output_reserve': limits.output}
    snapshot['status'] = ('disabled' if not configured else 'misconfigured' if timeout is None else
                          'saturated' if snapshot['active'] >= workers and snapshot['queued'] >= pending else 'ready')
    return snapshot

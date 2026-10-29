"""Capture console logging records without request bodies, headers, or frame locals."""
from datetime import datetime, timezone
import logging
import traceback

from app.integrations.assistant_safety import scrub


class ErrorReportHandler(logging.Handler):
    def __init__(self, repository):
        super().__init__(logging.WARNING)
        self.repository = repository

    def emit(self, record):
        try:
            details = f'{record.pathname}:{record.lineno} in {record.funcName}\n{record.getMessage()}'
            if record.exc_info and record.exc_info[1] is not None:
                exception = record.exc_info[1]
                seen = set()
                while exception is not None and id(exception) not in seen and len(seen) < 8:
                    seen.add(id(exception))
                    details += '\nTraceback (most recent call last):\n'
                    for frame in traceback.extract_tb(exception.__traceback__):
                        # No locals or source lines: both may contain submitted data.
                        details += f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
                    details += f'{type(exception).__qualname__}: {exception}\n'
                    exception = exception.__cause__ or (None if exception.__suppress_context__ else exception.__context__)
            safe_details = scrub(details)
            if len(safe_details) > 16000:
                marker = '\n[truncated at 16000 characters]'
                safe_details = safe_details[:16000 - len(marker)] + marker
            self.repository.append(
                datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                record.levelname, scrub(record.name)[:200], safe_details,
            )
        except Exception:
            # Diagnostics must never break a request or recursively log a storage error.
            pass


def install_error_reporting(repository):
    handler = ErrorReportHandler(repository)
    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, ErrorReportHandler):
            root.removeHandler(existing)
    root.addHandler(handler)
    # Gunicorn logs may not propagate to the root logger.
    gunicorn = logging.getLogger('gunicorn.error')
    if not gunicorn.propagate:
        for existing in list(gunicorn.handlers):
            if isinstance(existing, ErrorReportHandler):
                gunicorn.removeHandler(existing)
        gunicorn.addHandler(handler)
    return handler

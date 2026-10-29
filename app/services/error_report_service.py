"""Safe admin presentation and portable diagnostic export."""
from datetime import datetime, timezone
import json
import sqlite3
import re
from urllib.parse import urlsplit

from app.integrations.assistant_safety import scrub


def list_errors(repository):
    # Scrub again so credentials configured after capture are protected too.
    try:
        return scrub(repository.recent())
    except (OSError, sqlite3.Error):
        return [{'id': None, 'created_at': datetime.now(timezone.utc).isoformat(),
                 'level': 'ERROR', 'logger': 'manavote.diagnostics',
                 'details': 'Diagnostic storage is unavailable. Inspect the server console and check storage permissions/free space.'}]


def export_errors(repository):
    return json.dumps({
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Server warnings/errors and signed-in browser JavaScript errors; latest 200 records; each detail capped at 16000 characters. No historical container logs.',
        'errors': list_errors(repository),
    }, ensure_ascii=False, indent=2)


def capture_browser_error(repository, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('kind'), str) or payload['kind'] not in {'console.error', 'error', 'unhandledrejection'}:
        raise ValueError('Invalid browser error')
    fields = {'message': 6000, 'stack': 8000, 'page': 300}
    if any(not isinstance(payload.get(key, ''), str) or len(payload.get(key, '')) > limit for key, limit in fields.items()):
        raise ValueError('Invalid browser error')
    if not payload.get('message', '').strip():
        raise ValueError('Invalid browser error')
    def clean_url(match):
        try:
            parts = urlsplit(match.group())
            return parts.scheme + '://' + (parts.hostname or '') + parts.path
        except ValueError:
            return '[URL]'
    page = urlsplit(payload.get('page', ''))
    # Store path only, even when a client submits a full URL or query string.
    details = f"Page: {page.path}\n{payload['message']}\n{payload.get('stack', '')}"
    details = scrub(re.sub(r'https?://[^\s<>\"\')]+', clean_url, details))[:16000]
    try:
        repository.append(datetime.now(timezone.utc).isoformat(), 'ERROR', 'browser.' + payload['kind'], details)
    except (OSError, sqlite3.Error):
        pass  # A failed upload must not generate another browser/server error loop.

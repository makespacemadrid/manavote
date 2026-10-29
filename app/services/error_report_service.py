"""Safe admin presentation and portable diagnostic export."""
from datetime import datetime, timezone
import json
import sqlite3

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
        'scope': 'Server warnings/errors; latest 200 records; each detail capped at 16000 characters. No browser console or historical container logs.',
        'errors': list_errors(repository),
    }, ensure_ascii=False, indent=2)

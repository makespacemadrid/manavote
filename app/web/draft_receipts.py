"""Acknowledge a successful web submission without storing draft contents."""
import re
from flask import request, session


def complete_draft(key):
    nonce = request.form.get('_draft_nonce', '')
    if len(key) <= 400 and re.fullmatch(r'[A-Za-z0-9-]{1,80}', nonce):
        receipts = session.get('_draft_receipts', [])
        session['_draft_receipts'] = (receipts + [{'key':key, 'nonce':nonce}])[-4:]

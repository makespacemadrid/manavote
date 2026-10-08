"""Model payload budgets and credential boundaries, independent of HTTP/Flask."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from translations import TRANSLATIONS

REDACTED = "[REDACTED]"
INPUT_MESSAGE = "That message is too large. Please send a shorter question."
CONTEXT_MESSAGE = "The assistant context is too large. Use /reset or request fewer results. Previous actions may already have completed."
SECRET_MESSAGE = "Please remove credentials or sensitive fields from your request."
_SECRET_NAMES = (
    "SECRET_KEY", "ADMIN_API_KEY", "MCP_API_KEY", "OCABRA_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "OIDC_CLIENT_SECRET",
    "SMTP_PASSWORD", "EMAIL_PASSWORD", "ADMIN_PASSWORD", "ADMIN_BOOTSTRAP_PASSWORD",
)
_FIELD = re.compile(r"password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|private[_-]?key|^token$|^cookie$", re.I)
_URL = re.compile(r"https?://[^\s<>\"']+")
_ASSIGNMENT = re.compile(r"\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)", re.I)
_BEARER = re.compile(r"\bBearer\s+[^\s,;}\"']+", re.I)


def localized(message, language_code=None):
    language = str(language_code or "en").lower().split("-", 1)[0].split("_", 1)[0]
    return TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(message, message)


class SafetyRejection(ValueError):
    def __init__(self, reason_code, message):
        self.reason_code = reason_code
        self.message = message
        super().__init__(reason_code)


@dataclass(frozen=True)
class ModelLimits:
    context: int = 32768
    input: int = 4096
    output: int = 1024

    @classmethod
    def from_env(cls):
        values = []
        for name, default in (("TELEGRAM_AGENT_CONTEXT_BUDGET", 32768),
                              ("TELEGRAM_AGENT_INPUT_BUDGET", 4096),
                              ("TELEGRAM_AGENT_OUTPUT_RESERVE", 1024)):
            raw = os.getenv(name, str(default))
            if not raw.isascii() or not raw.isdecimal() or int(raw) < 1:
                raise ValueError(f"{name} must be a positive integer")
            values.append(int(raw))
        limits = cls(*values)
        if limits.input + limits.output >= limits.context:
            raise ValueError("TELEGRAM_AGENT_CONTEXT_BUDGET must exceed input budget plus output reserve")
        return limits

    def check_input(self, text):
        if len(text.encode("utf-8")) > self.input:
            raise SafetyRejection("input_budget_exceeded", INPUT_MESSAGE)

    def size(self, messages, tools):
        # One serialized UTF-8 byte per estimated token, plus framing allowance.
        # This intentionally overestimates common byte-based model tokenizers.
        encoded = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False).encode("utf-8")
        return len(encoded) + 256 + 64 * len(messages)

    def fit(self, system, history, current, tools):
        groups = history_groups(history)
        while True:
            messages = [system, *(message for group in groups for message in group), *current]
            if self.size(messages, tools) + self.output <= self.context:
                return messages
            if not groups:
                raise SafetyRejection("context_budget_exceeded", CONTEXT_MESSAGE)
            groups.pop(0)


def history_groups(history):
    """Keep complete user-led groups and discard malformed/orphaned tool sequences."""
    groups = []
    for message in history:
        if message.get("role") == "user":
            groups.append([])
        if groups:
            groups[-1].append(message)
    valid = []
    for group in groups:
        pending = set()
        ok = True
        for message in group:
            role = message.get("role")
            if pending and role != "tool":
                ok = False
            if role == "assistant":
                pending.update(call.get("id") for call in message.get("tool_calls", []) or [])
            elif role == "tool":
                call_id = message.get("tool_call_id")
                if call_id not in pending:
                    ok = False
                pending.discard(call_id)
        if ok and not pending:
            valid.append(group)
    return valid


def scrub(value):
    """Redact configured values and conventional secret fields; no free-text guarantee."""
    if isinstance(value, dict):
        return {key: REDACTED if _FIELD.search(str(key)) else scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if not isinstance(value, str):
        return value
    # Tool arguments/results often contain JSON nested inside a string.
    if value.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            pass
        else:
            cleaned = scrub(parsed)
            if cleaned != parsed:
                return json.dumps(cleaned, ensure_ascii=False)
    def clean_url(match):
        original = match.group(0)
        try:
            parts = urlsplit(original)
            host = parts.netloc.rsplit("@", 1)[-1]
            query = parse_qsl(parts.query, keep_blank_values=True)
            cleaned = [(key, REDACTED if _FIELD.search(key) else item) for key, item in query]
            if host == parts.netloc and cleaned == query:
                return original
            return urlunsplit((parts.scheme, host, parts.path, urlencode(cleaned), parts.fragment))
        except ValueError:
            return REDACTED
    result = _URL.sub(clean_url, value)
    result = _ASSIGNMENT.sub(lambda m: f"{m.group(1)}={REDACTED}", result)
    result = _BEARER.sub(f"Bearer {REDACTED}", result)
    for secret in sorted({os.getenv(name, "") for name in _SECRET_NAMES} - {""}, key=len, reverse=True):
        result = result.replace(secret, REDACTED)
    return result


def check_arguments(arguments):
    if scrub(arguments) != arguments:
        raise SafetyRejection("credential_input_rejected", SECRET_MESSAGE)

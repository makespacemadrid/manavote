"""Voting-mode policy: which channels (web/Telegram) accept poll and proposal votes.

Each function takes a `get_setting_value(key, default)` callable rather than
reading settings directly, so the policy logic can be unit-tested without a
database or Flask app context.
"""

from app.services.proposal_vote_service import (
    can_record_proposal_vote_source,
    normalize_proposal_vote_mode,
)
from app.services.settings_service import get_enum_setting

_VOTE_MODES = {"both", "web_only", "telegram_only"}


def get_poll_vote_mode(get_setting_value):
    return get_enum_setting(get_setting_value, "poll_vote_mode", "both", _VOTE_MODES)


def is_web_poll_voting_enabled(get_setting_value):
    return get_poll_vote_mode(get_setting_value) in {"both", "web_only"}


def is_telegram_poll_voting_enabled(get_setting_value):
    return get_poll_vote_mode(get_setting_value) in {"both", "telegram_only"}


def require_linked_telegram_for_votes(get_setting_value):
    return str(get_setting_value("telegram_require_linked_vote", "false")).lower() == "true"


def get_proposal_vote_mode(get_setting_value):
    mode = get_enum_setting(get_setting_value, "proposal_vote_mode", "both", _VOTE_MODES)
    return normalize_proposal_vote_mode(mode)


def is_web_proposal_voting_enabled(get_setting_value):
    return get_proposal_vote_mode(get_setting_value) in {"both", "web_only"}


def can_record_proposal_vote(get_setting_value, source):
    return can_record_proposal_vote_source(get_proposal_vote_mode(get_setting_value), source)


def is_registration_enabled(get_setting_value):
    return str(get_setting_value("registration_enabled", "true")).lower() == "true"

"""Proposal vote-mode policy helpers."""

VALID_PROPOSAL_VOTE_MODES = {"both", "web_only", "telegram_only"}


def normalize_proposal_vote_mode(raw_mode) -> str:
    mode = str(raw_mode or "both").strip().lower()
    if mode not in VALID_PROPOSAL_VOTE_MODES:
        return "both"
    return mode


def can_record_proposal_vote_source(mode: str, source: str) -> bool:
    normalized_mode = normalize_proposal_vote_mode(mode)
    normalized_source = (source or "").strip().lower()

    if normalized_source == "web":
        return normalized_mode in {"both", "web_only"}
    if normalized_source == "telegram":
        return normalized_mode in {"both", "telegram_only"}
    return False

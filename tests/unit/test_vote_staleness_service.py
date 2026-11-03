from datetime import datetime, timedelta

from app.services.vote_staleness_service import (
    STALE_AFTER_DAYS,
    apply_age_staleness,
    is_due_for_age_staleness,
    is_vote_stale,
)


def test_is_due_for_age_staleness_before_and_after_the_threshold():
    created_at = "2026-01-01 00:00:00"
    just_before = datetime(2026, 1, 1) + timedelta(days=STALE_AFTER_DAYS) - timedelta(seconds=1)
    just_after = datetime(2026, 1, 1) + timedelta(days=STALE_AFTER_DAYS)

    assert is_due_for_age_staleness(created_at, now=just_before) is False
    assert is_due_for_age_staleness(created_at, now=just_after) is True


def test_is_due_for_age_staleness_handles_z_suffixed_timestamps():
    # Some callers (JS-submitted / OIDC-derived data) attach a 'Z' suffix; this
    # app otherwise treats all stored timestamps as naive, so it must not blow
    # up comparing a tz-aware parse against a naive `now`.
    created_at = "2026-01-01T00:00:00Z"
    assert is_due_for_age_staleness(created_at, now=datetime(2026, 4, 1)) is True
    assert is_due_for_age_staleness(created_at, now=datetime(2026, 1, 2)) is False


class _FakeProposalRepo:
    def __init__(self):
        self.bumped = []

    def bump_votes_valid_after_id(self, proposal_id, vote_id_cutoff):
        self.bumped.append((proposal_id, vote_id_cutoff))


class _FakeVoteRepo:
    def __init__(self, max_id):
        self._max_id = max_id

    def max_vote_id(self, proposal_id):
        return self._max_id


def test_apply_age_staleness_noop_for_recent_active_proposal():
    proposal = {"id": 1, "status": "active", "created_at": datetime.now().isoformat(), "votes_valid_after_id": None}
    proposal_repo = _FakeProposalRepo()
    vote_repo = _FakeVoteRepo(max_id=5)

    result = apply_age_staleness(proposal_repo, vote_repo, proposal)

    assert result is None
    assert proposal_repo.bumped == []


def test_apply_age_staleness_bumps_once_for_old_active_proposal():
    old_created_at = (datetime.now() - timedelta(days=STALE_AFTER_DAYS + 1)).isoformat()
    proposal = {"id": 7, "status": "active", "created_at": old_created_at, "votes_valid_after_id": None}
    proposal_repo = _FakeProposalRepo()
    vote_repo = _FakeVoteRepo(max_id=12)

    result = apply_age_staleness(proposal_repo, vote_repo, proposal)

    assert result == 12
    assert proposal_repo.bumped == [(7, 12)]


def test_apply_age_staleness_does_not_rebump_once_a_cutoff_exists():
    # Regression test: if this re-bumped to "current max vote id" on every
    # call, a fresh recast after the proposal went stale would immediately be
    # swept up by the next process_proposal() call's re-evaluation, and could
    # never "graduate" past the cutoff.
    old_created_at = (datetime.now() - timedelta(days=STALE_AFTER_DAYS + 1)).isoformat()
    proposal = {"id": 7, "status": "active", "created_at": old_created_at, "votes_valid_after_id": 3}
    proposal_repo = _FakeProposalRepo()
    vote_repo = _FakeVoteRepo(max_id=99)  # a fresh vote has since been cast

    result = apply_age_staleness(proposal_repo, vote_repo, proposal)

    assert result == 3
    assert proposal_repo.bumped == []


def test_apply_age_staleness_ignores_non_active_proposals():
    old_created_at = (datetime.now() - timedelta(days=STALE_AFTER_DAYS + 1)).isoformat()
    proposal = {"id": 9, "status": "approved", "created_at": old_created_at, "votes_valid_after_id": None}
    proposal_repo = _FakeProposalRepo()
    vote_repo = _FakeVoteRepo(max_id=4)

    result = apply_age_staleness(proposal_repo, vote_repo, proposal)

    assert result is None
    assert proposal_repo.bumped == []


def test_is_vote_stale():
    assert is_vote_stale(vote_id=5, votes_valid_after_id=10) is True
    assert is_vote_stale(vote_id=10, votes_valid_after_id=10) is True
    assert is_vote_stale(vote_id=11, votes_valid_after_id=10) is False
    assert is_vote_stale(vote_id=1, votes_valid_after_id=None) is False
    assert is_vote_stale(vote_id=1, votes_valid_after_id=0) is False

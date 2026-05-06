import sqlite3

from app.repositories.vote_repo import VoteRepository


def _setup_votes_table(conn):
    conn.execute(
        """
        CREATE TABLE votes (
            proposal_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            vote TEXT NOT NULL,
            UNIQUE(proposal_id, member_id)
        )
        """
    )
    conn.commit()


def test_upsert_proposal_vote_replaces_existing_member_vote():
    conn = sqlite3.connect(":memory:")
    _setup_votes_table(conn)
    repo = VoteRepository(conn)

    repo.upsert_proposal_vote(1, 5, "in_favor")
    repo.upsert_proposal_vote(1, 5, "against")

    assert repo.get_member_vote(1, 5) == "against"


def test_get_counts_reflects_latest_votes():
    conn = sqlite3.connect(":memory:")
    _setup_votes_table(conn)
    repo = VoteRepository(conn)

    repo.upsert_proposal_vote(2, 10, "in_favor")
    repo.upsert_proposal_vote(2, 11, "against")
    repo.upsert_proposal_vote(2, 11, "in_favor")

    approve, reject = repo.get_counts(2)
    assert approve == 2
    assert reject == 0

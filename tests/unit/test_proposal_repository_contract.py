import sqlite3

from app.repositories.proposal_repo import ProposalRepository


def _setup_tables(conn):
    conn.execute(
        """
        CREATE TABLE proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            url TEXT,
            created_by INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            basic_supplies INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            content TEXT NOT NULL
        )
        """
    )
    conn.commit()


def test_create_inserts_proposal_with_given_fields():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_tables(conn)
    repo = ProposalRepository(conn)

    proposal_id = repo.create("LED Strips", "For the workshop", 15.0, "http://example.com", 1, basic_supplies=1)

    row = repo.get_by_id(proposal_id)
    assert row["title"] == "LED Strips"
    assert row["amount"] == 15.0
    assert row["basic_supplies"] == 1


def test_create_auto_clears_basic_supplies_over_20_euros_and_logs_comment():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_tables(conn)
    repo = ProposalRepository(conn)

    proposal_id = repo.create("Soldering Station", "", 45.0, "", 1, basic_supplies=1)

    row = repo.get_by_id(proposal_id)
    assert row["basic_supplies"] == 0
    comment = conn.execute("SELECT content FROM comments WHERE proposal_id = ?", (proposal_id,)).fetchone()
    assert "Auto-removed basic supplies flag" in comment["content"]


def test_create_leaves_basic_supplies_untouched_under_threshold():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_tables(conn)
    repo = ProposalRepository(conn)

    proposal_id = repo.create("Glue sticks", "", 5.0, "", 1, basic_supplies=1)

    row = repo.get_by_id(proposal_id)
    assert row["basic_supplies"] == 1
    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0


def test_create_leaves_non_basic_supplies_proposal_untouched_regardless_of_amount():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_tables(conn)
    repo = ProposalRepository(conn)

    proposal_id = repo.create("Server rack", "", 500.0, "", 1, basic_supplies=0)

    row = repo.get_by_id(proposal_id)
    assert row["basic_supplies"] == 0
    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0

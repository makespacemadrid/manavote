"""Read-side regression contracts, using real repositories without a Flask request."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.db.migrations import run_migrations
from app.services.budget_service import build_budget_page
from app.services.proposal_page_service import build_proposal_page

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def page_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript((Path(__file__).resolve().parents[2] / "app/db/schema.sql").read_text())
    run_migrations(connection.cursor())
    connection.executemany(
        "INSERT INTO members (id, username, password_hash) VALUES (?, ?, 'unused')",
        [(1, "alice"), (2, "bob")],
    )
    connection.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [("threshold_basic", "50"), ("threshold_default", "100"), ("threshold_over50", "100")],
    )
    connection.executemany(
        """INSERT INTO proposals
           (id, title, amount, created_by, status, basic_supplies, created_at,
            over_budget_at, processed_at, purchased_at)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
        [
            (1, "Recent basic", 10, "active", 1, "2026-10-07T12:00:00Z", None, None, None),
            (2, "Boundary expensive", 60, "active", 0, "2026-09-08 12:00:00", None, None, None),
            (3, "Standard pending purchase", 20, "approved", 0, "2026-09-30", "2026-09-01", "2026-10-02", None),
            (4, "Purchased expensive", 70, "approved", 0, "2026-10-01", None, "2026-10-03", "2026-10-03"),
            (5, "Rejected expensive", 80, "rejected", 0, "2026-09-28", None, None, None),
            (6, "Waiting for budget", 30, "over_budget", 0, "2026-09-29", "2026-10-01", None, None),
        ],
    )
    connection.executemany(
        "INSERT INTO activity_log (amount, description, created_at) VALUES (?, 'entry', ?)",
        [(100, "2026-10-01"), (-5, "2026-10-01"), (-20, "2026-10-02"), (-70, "2026-10-03")],
    )
    connection.executemany(
        "INSERT INTO votes (proposal_id, member_id, vote) VALUES (1, ?, ?)",
        [(1, "in_favor"), (2, "against")],
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.mark.parametrize("filter_type,expected", [
    ("active", [1, 2]), ("old", [2]), ("recent", [1]),
    ("basic", [1]), ("approved", [4, 3]), ("over_budget", [6]),
    ("purchased", [4]), ("not_purchased", [3]), ("standard", [3]),
    ("expensive", [4, 2]), ("all", [1, 4, 3, 6, 5, 2]),
    ("unknown' OR 1=1 --", [1, 4, 3, 6, 5, 2]),
])
def test_proposal_filters_preserve_membership_order_and_thirty_day_boundary(page_db, filter_type, expected):
    model = build_proposal_page(page_db, member_id=2, filter_type=filter_type, now=NOW)
    assert [p["id"] for p in model["proposals"]] == expected
    assert model["total_count"] == 6


def test_proposal_balances_votes_ages_and_chip_totals(page_db):
    model = build_proposal_page(page_db, member_id=2, filter_type="active", now=NOW)
    recent, old = model["proposals"]
    assert recent["creator"] == "alice"
    assert (recent["approve_count"], recent["reject_count"], recent["net_votes"], recent["user_vote"]) == (1, 1, 0, "against")
    assert recent["min_backers"] == 1 and old["min_backers"] == 2
    assert (recent["age_days"], recent["old_age_threshold"]) == (1, None)
    assert (old["age_days"], old["old_age_threshold"]) == (30, 30)
    assert old["user_vote"] is None
    assert model["current_budget"] == 5
    assert [entry["balance"] for entry in model["budget_history"]] == [5, 75, 95, 100]
    assert (model["basic_votes"], model["standard_votes"], model["expensive_votes"]) == (1, 2, 2)
    assert {name: model[name] for name in (
        "active_proposals_sum", "old_proposals_sum", "recent_proposals_sum", "committed",
        "pending_purchase_sum", "purchased_sum", "approved_sum", "basic_sum",
        "standard_sum", "expensive_sum", "all_sum",
    )} == {
        "active_proposals_sum": 70, "old_proposals_sum": 60, "recent_proposals_sum": 10,
        "committed": 30, "pending_purchase_sum": 20, "purchased_sum": 70,
        "approved_sum": 90, "basic_sum": 10, "standard_sum": 20,
        "expensive_sum": 210, "all_sum": 270,
    }


def test_budget_timeline_preserves_pending_release_and_cash_signs(page_db):
    model = build_budget_page(page_db)
    days = {entry["day"]: entry for entry in model["daily_budget"]}
    assert days["2026-09-01"]["pending"] == 20
    assert days["2026-10-01"] == {
        "day": "2026-10-01", "cash_in": 100, "cash_out": -5, "approved": 0,
        "cash_balance": 95, "pending": 50, "proposals": 70,
    }
    assert days["2026-10-02"]["pending"] == 30
    assert days["2026-10-02"]["approved"] == -20
    assert days["2026-10-03"]["cash_out"] == -70
    assert days["2026-10-03"]["cash_balance"] == model["current_balance"] == 5
    assert len(model["calendar_items"]) == 10
    # These read services neither close the connection nor write to it.
    assert page_db.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 2


@pytest.mark.parametrize("sort_by,key,reverse", [
    ("date_asc", "created_at", False), ("date_desc", "created_at", True),
    ("amount_asc", "amount", False), ("amount_desc", "amount", True),
    ("unknown; DROP TABLE proposals", "created_at", True),
])
def test_calendar_sort_and_pagination_preserve_global_order(page_db, sort_by, key, reverse):
    whole = build_budget_page(page_db, sort_by=sort_by)
    values = [entry[key] for entry in whole["calendar_items"]]
    assert values == sorted(values, reverse=reverse)
    first = build_budget_page(page_db, sort_by=sort_by, per_page=3)
    second = build_budget_page(page_db, sort_by=sort_by, page=2, per_page=3)
    assert len(first["calendar_items"]) == len(second["calendar_items"]) == 3
    assert first["total_pages"] == second["total_pages"] == 4
    assert [dict(row) for row in second["calendar_items"]] == [dict(row) for row in whole["calendar_items"][3:6]]
    assert first["daily_budget"] == second["daily_budget"] == whole["daily_budget"]


def test_empty_read_models_have_zero_balances_and_one_calendar_page(page_db):
    for table in ("votes", "proposals", "activity_log"):
        page_db.execute(f"DELETE FROM {table}")
    budget = build_budget_page(page_db)
    proposals = build_proposal_page(page_db, member_id=1, now=NOW)
    assert budget["daily_budget"] == budget["calendar_items"] == []
    assert budget["current_balance"] == proposals["current_budget"] == 0
    assert budget["total_pages"] == 1
    assert proposals["proposals"] == proposals["budget_history"] == []
    assert proposals["total_count"] == proposals["all_sum"] == 0


@pytest.mark.parametrize("path,builder", [
    ("/budget", "build_budget_page"), ("/proposals", "build_proposal_page"),
])
def test_page_routes_close_database_when_read_service_fails(monkeypatch, path, builder):
    from unittest.mock import Mock

    from app import app
    from app.web.routes import main_routes, proposal_routes

    connection = Mock()
    monkeypatch.setattr(main_routes, "get_db", lambda: connection)
    def fail(*_args, **_kwargs):
        raise sqlite3.OperationalError("read failed")

    monkeypatch.setattr(proposal_routes, builder, fail)
    monkeypatch.setitem(app.config, "TESTING", True)
    client = app.test_client()
    with client.session_transaction() as user_session:
        user_session.update(member_id=2, username="bob", is_admin=0)
    with pytest.raises(sqlite3.OperationalError, match="read failed"):
        client.get(path)
    connection.close.assert_called_once_with()

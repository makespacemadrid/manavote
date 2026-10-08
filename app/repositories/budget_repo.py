import sqlite3


class BudgetRepository:
    def __init__(self, conn):
        self.conn = conn

    def current_budget(self):
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(amount) as total FROM activity_log")
        total = cur.fetchone()["total"]
        return total if total else 0

    def history(self):
        return self.conn.execute("SELECT * FROM activity_log ORDER BY created_at ASC").fetchall()

    def calendar_count(self):
        return self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM proposals) + (SELECT COUNT(*) FROM activity_log)"
        ).fetchone()[0]

    def calendar_items(self, sort_by, limit, offset):
        order_clause = {
            "date_asc": "created_at ASC",
            "amount_desc": "amount DESC",
            "amount_asc": "amount ASC",
        }.get(sort_by, "created_at DESC")
        return self.conn.execute(
            f"""SELECT * FROM (
                SELECT id, created_at, amount, 'proposal' AS item_type, title, status,
                       NULL AS description, id AS proposal_id FROM proposals
                UNION ALL
                SELECT id, created_at, amount, 'activity' AS item_type, NULL AS title,
                       NULL AS status, description, proposal_id FROM activity_log
            ) AS calendar_items ORDER BY {order_clause} LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()

    def cash_by_day(self):
        return self.conn.execute(
            """SELECT date(created_at) AS day,
                      SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS cash_in,
                      SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS cash_out
               FROM activity_log GROUP BY date(created_at)"""
        ).fetchall()

    def add_log(self, amount, description, created_by=None, proposal_id=None):
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO activity_log (amount, description, created_by, proposal_id) VALUES (?, ?, ?, ?)",
                (amount, description, created_by, proposal_id),
            )
        except sqlite3.OperationalError as exc:
            if "no column named proposal_id" not in str(exc):
                raise
            cur.execute(
                "INSERT INTO activity_log (amount, description, created_by) VALUES (?, ?, ?)",
                (amount, description, created_by),
            )

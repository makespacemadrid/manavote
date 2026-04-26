class BudgetRepository:
    def __init__(self, conn):
        self.conn = conn

    def current_budget(self):
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(amount) as total FROM activity_log")
        total = cur.fetchone()["total"]
        return total if total else 0

    def add_log(self, amount, description, created_by=None, proposal_id=None):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO activity_log (amount, description, created_by, proposal_id) VALUES (?, ?, ?, ?)",
            (amount, description, created_by, proposal_id),
        )

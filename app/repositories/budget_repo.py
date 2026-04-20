class BudgetRepository:
    def __init__(self, conn):
        self.conn = conn

    def current_budget(self):
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(amount) as total FROM budget_log")
        total = cur.fetchone()["total"]
        return total if total else 0

    def add_log(self, amount, description):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO budget_log (amount, description) VALUES (?, ?)", (amount, description))

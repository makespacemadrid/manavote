class ProposalRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_by_id(self, proposal_id):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
        return cur.fetchone()

    def mark_approved(self, proposal_id, processed_at):
        cur = self.conn.cursor()
        cur.execute("UPDATE proposals SET status = 'approved', processed_at = ? WHERE id = ?", (processed_at, proposal_id))

    def mark_over_budget(self, proposal_id, processed_at):
        cur = self.conn.cursor()
        cur.execute("UPDATE proposals SET status = 'over_budget', processed_at = ?, over_budget_at = ? WHERE id = ?", (processed_at, processed_at, proposal_id))

    def list_over_budget(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, title, amount, basic_supplies FROM proposals WHERE status = 'over_budget' ORDER BY created_at ASC")
        return cur.fetchall()

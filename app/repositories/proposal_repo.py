class ProposalRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, title, description, amount, url, created_by, basic_supplies, image_filename=None):
        """Insert a proposal; auto-clears basic_supplies when amount exceeds the €20 threshold."""
        cur = self.conn.cursor()
        if image_filename is None:
            # Keep compatibility with databases that predate the image column.
            cur.execute(
                "INSERT INTO proposals (title, description, amount, url, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, amount, url, created_by, basic_supplies),
            )
        else:
            cur.execute(
                "INSERT INTO proposals "
                "(title, description, amount, url, image_filename, created_by, basic_supplies) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, description, amount, url, image_filename, created_by, basic_supplies),
            )
        proposal_id = cur.lastrowid
        if basic_supplies and amount > 20.0:
            cur.execute("UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,))
            cur.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (proposal_id, created_by, "Auto-removed basic supplies flag: amount over €20"),
            )
        self.conn.commit()
        return proposal_id

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

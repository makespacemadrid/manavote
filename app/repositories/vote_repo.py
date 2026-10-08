class VoteRepository:
    def __init__(self, conn):
        self.conn = conn

    def delete_for_proposal(self, proposal_id):
        self.conn.execute("DELETE FROM votes WHERE proposal_id = ?", (proposal_id,))

    def delete_member_vote(self, proposal_id, member_id):
        self.conn.execute(
            "DELETE FROM votes WHERE proposal_id = ? AND member_id = ?",
            (proposal_id, member_id),
        )

    def get_counts(self, proposal_id):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'", (proposal_id,))
        approve_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'against'", (proposal_id,))
        reject_count = cur.fetchone()[0]
        return approve_count, reject_count

    def upsert_proposal_vote(self, proposal_id, member_id, vote):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO votes (proposal_id, member_id, vote) VALUES (?, ?, ?)",
            (proposal_id, member_id, vote),
        )
        self.conn.commit()

    def get_member_vote(self, proposal_id, member_id):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
            (proposal_id, member_id),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def list_with_members(self, proposal_id):
        return self.conn.execute(
            "SELECT v.*, m.username FROM votes v JOIN members m ON v.member_id = m.id WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchall()

    def insert_creator_vote(self, proposal_id, member_id):
        self.conn.execute(
            "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, 'in_favor')", (proposal_id, member_id)
        )

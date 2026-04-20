class VoteRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_counts(self, proposal_id):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'", (proposal_id,))
        approve_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'against'", (proposal_id,))
        reject_count = cur.fetchone()[0]
        return approve_count, reject_count

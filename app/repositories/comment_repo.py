class CommentRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_by_id(self, comment_id):
        return self.conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()

    def delete(self, comment_id):
        self.conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))

    def update_content(self, comment_id, content):
        self.conn.execute("UPDATE comments SET content = ? WHERE id = ?", (content, comment_id))

    def delete_for_proposal(self, proposal_id):
        self.conn.execute("DELETE FROM comments WHERE proposal_id = ?", (proposal_id,))

    def create(self, proposal_id, member_id, content):
        return self.conn.execute(
            "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
            (proposal_id, member_id, content),
        ).lastrowid

    def list_with_members(self, proposal_id):
        return self.conn.execute(
            "SELECT c.*, m.username FROM comments c JOIN members m ON c.member_id = m.id WHERE proposal_id = ? ORDER BY c.created_at DESC",
            (proposal_id,),
        ).fetchall()

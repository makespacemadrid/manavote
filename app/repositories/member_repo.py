class MemberRepository:
    def __init__(self, conn):
        self.conn = conn

    def count(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM members")
        return cur.fetchone()[0]

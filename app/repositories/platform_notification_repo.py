"""Durable notification keys shared by web, MCP and scheduler workers."""
class PlatformNotificationRepository:
    TABLES = {'proposal': 'proposals', 'poll': 'polls', 'group_purchase': 'group_purchases'}

    def __init__(self, conn):
        self.conn = conn

    def queue(self, key, kind, item_id, deadline=None):
        self.conn.execute('INSERT OR IGNORE INTO platform_notifications(event_key,kind,item_id,deadline) VALUES (?,?,?,?)',
                          (key, kind, item_id, deadline))

    def pending(self, event_key=None):
        if event_key is not None:
            return self.conn.execute("SELECT * FROM platform_notifications WHERE status='pending' AND event_key=?",(event_key,)).fetchall()
        return self.conn.execute("SELECT * FROM platform_notifications WHERE status='pending' ORDER BY rowid LIMIT 100").fetchall()

    def claim(self, key):
        return self.conn.execute("UPDATE platform_notifications SET status='sending' WHERE event_key=? AND status='pending'", (key,)).rowcount == 1

    def finish(self, key, status):
        self.conn.execute('UPDATE platform_notifications SET status=?,attempted_at=CURRENT_TIMESTAMP WHERE event_key=?', (status,key))

    def item(self, kind, item_id):
        return self.conn.execute(f'SELECT * FROM {self.TABLES[kind]} WHERE id=?', (item_id,)).fetchone()

    def settings(self):
        return dict(self.conn.execute("SELECT key,value FROM settings WHERE key IN ('url','timezone','proposal_vote_mode','poll_vote_mode')").fetchall())

    def creator(self, member_id):
        row = self.conn.execute('SELECT username FROM members WHERE id=?', (member_id,)).fetchone()
        return row[0].split('@')[0] if row else 'unknown'

    def components(self, item_id):
        return self.conn.execute('SELECT name,unit_price FROM group_purchase_components WHERE group_purchase_id=? ORDER BY position,id', (item_id,)).fetchall()

    def costs(self, item_id):
        return self.conn.execute('SELECT label,amount FROM group_purchase_shared_costs WHERE group_purchase_id=? ORDER BY id', (item_id,)).fetchall()

    def deadlines(self):
        return self.conn.execute("""SELECT 'proposal' AS kind,id,voting_deadline AS deadline FROM proposals WHERE status='active' AND voting_deadline IS NOT NULL
            UNION ALL SELECT 'poll',id,closes_at FROM polls WHERE status='open' AND closes_at IS NOT NULL
            UNION ALL SELECT 'group_purchase',id,deadline FROM group_purchases WHERE status='open' AND deadline IS NOT NULL""").fetchall()

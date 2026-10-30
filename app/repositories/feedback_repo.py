"""Administrator feedback management and member notifications."""
class FeedbackRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, feedback_id):
        return self.conn.execute('SELECT * FROM feedback WHERE id = ?', (feedback_id,)).fetchone()

    def set_public_reason(self, feedback_id, reason):
        self.conn.execute('UPDATE feedback SET public_reason=? WHERE id=?', (reason, feedback_id))

    def add_status_event(self, feedback_id, status, reason=''):
        self.conn.execute('INSERT INTO feedback_status_events(feedback_id,status,public_reason) VALUES (?,?,?)', (feedback_id, status, reason))

    def for_member(self, member_id):
        # Explicit projection: private notes/operator details never enter this read model.
        rows = self.conn.execute('''SELECT id,message,category,section,status,public_reason,created_at
            FROM feedback WHERE member_id=? ORDER BY id DESC LIMIT 100''', (member_id,)).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item['history'] = [dict(row) for row in self.conn.execute('''SELECT e.status,e.public_reason,e.created_at
                FROM feedback_status_events e JOIN feedback f ON f.id=e.feedback_id
                WHERE f.id=? AND f.member_id=? ORDER BY e.id''', (item['id'], member_id))]
        return items

    def resolve_status(self, feedback_id, status, actor):
        self.conn.execute("UPDATE feedback SET status=?, resolved_by=?, resolved_at=CASE WHEN ?='resolved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?", (status, actor, status, feedback_id))

    def notify(self, feedback):
        return self.conn.execute('INSERT INTO feedback_notifications(feedback_id,member_id,message) VALUES (?,?,?)', (feedback['id'], feedback['member_id'], feedback['message'][:250])).lastrowid

    def member(self, member_id):
        return self.conn.execute('SELECT * FROM members WHERE id=?', (member_id,)).fetchone()

    def preferences(self, member_id, enabled, language):
        self.conn.execute('UPDATE members SET feedback_telegram_notifications=?,feedback_notification_language=? WHERE id=?', (int(enabled), language, member_id))

    def delivery(self, notification_id):
        return self.conn.execute('SELECT * FROM feedback_notifications WHERE id=?', (notification_id,)).fetchone()

    def claim_delivery(self, notification_id):
        return self.conn.execute("UPDATE feedback_notifications SET telegram_status='sending' WHERE id=? AND telegram_status='pending'", (notification_id,)).rowcount

    def finish_delivery(self, notification_id, status):
        self.conn.execute("UPDATE feedback_notifications SET telegram_status=?,telegram_sent_at=CASE WHEN ?='sent' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?", (status, status, notification_id))

    def notifications(self, member_id):
        return [dict(r) for r in self.conn.execute('SELECT * FROM feedback_notifications WHERE member_id=? AND read_at IS NULL ORDER BY id DESC LIMIT 50', (member_id,))]

    def dismiss(self, notification_id, member_id):
        self.conn.execute('UPDATE feedback_notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND member_id=?', (notification_id, member_id))

    def notes(self, feedback_id):
        return [dict(r) for r in self.conn.execute('SELECT n.*,m.username FROM feedback_notes n JOIN members m ON m.id=n.author_id WHERE feedback_id=? ORDER BY n.id', (feedback_id,))]

    def add_note(self, feedback_id, actor, message):
        self.conn.execute('INSERT INTO feedback_notes(feedback_id,author_id,message) VALUES (?,?,?)', (feedback_id, actor, message))

    def edit_note(self, feedback_id, note_id, message):
        return self.conn.execute('UPDATE feedback_notes SET message=? WHERE id=? AND feedback_id=?', (message, note_id, feedback_id)).rowcount

    def delete_note(self, feedback_id, note_id):
        return self.conn.execute('DELETE FROM feedback_notes WHERE id=? AND feedback_id=?', (note_id, feedback_id)).rowcount

    def edit(self, feedback_id, message, category):
        self.conn.execute('UPDATE feedback SET message=?,category=? WHERE id=?', (message, category, feedback_id))

    def delete(self, feedback_id):
        self.conn.execute('DELETE FROM feedback_status_events WHERE feedback_id=?', (feedback_id,))
        self.conn.execute('DELETE FROM feedback_notes WHERE feedback_id=?', (feedback_id,))
        self.conn.execute('DELETE FROM feedback_notifications WHERE feedback_id=?', (feedback_id,))
        self.conn.execute('DELETE FROM feedback WHERE id=?', (feedback_id,))

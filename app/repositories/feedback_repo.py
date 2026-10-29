"""Administrator feedback management and member notifications."""
class FeedbackRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, feedback_id):
        return self.conn.execute('SELECT * FROM feedback WHERE id = ?', (feedback_id,)).fetchone()

    def resolve_status(self, feedback_id, status, actor):
        self.conn.execute("UPDATE feedback SET status=?, resolved_by=?, resolved_at=CASE WHEN ?='resolved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?", (status, actor, status, feedback_id))

    def notify(self, feedback):
        self.conn.execute('INSERT INTO feedback_notifications(feedback_id,member_id,message) VALUES (?,?,?)', (feedback['id'], feedback['member_id'], feedback['message'][:250]))

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
        self.conn.execute('DELETE FROM feedback_notes WHERE feedback_id=?', (feedback_id,))
        self.conn.execute('DELETE FROM feedback_notifications WHERE feedback_id=?', (feedback_id,))
        self.conn.execute('DELETE FROM feedback WHERE id=?', (feedback_id,))

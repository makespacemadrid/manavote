import json


class PollRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, question, options, created_by, allow_multiple=False):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO polls (question, options_json, created_by, status, allow_multiple) VALUES (?, ?, ?, 'open', ?)",
            (question, json.dumps(options), created_by, 1 if allow_multiple else 0),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_by_id(self, poll_id):
        return self.conn.execute('SELECT * FROM polls WHERE id = ?', (poll_id,)).fetchone()

    def list_for_page(self):
        return self.conn.execute('''SELECT p.*, m.username AS creator FROM polls p
            JOIN members m ON m.id = p.created_by ORDER BY p.created_at DESC''').fetchall()

    def votes_for_page(self, poll_id):
        return self.conn.execute('''SELECT pv.option_index, pv.created_at,
            COALESCE(NULLIF(mm.telegram_username, ''), mm.username, '') AS username,
            CASE WHEN COALESCE(NULLIF(mm.telegram_username, ''), '') = '' THEN 0 ELSE 1 END AS is_linked_username
            FROM poll_votes pv LEFT JOIN members mm ON mm.id = pv.member_id
            WHERE pv.poll_id = ? ORDER BY pv.created_at ASC''', (poll_id,)).fetchall()

    def member_votes(self, poll_id, member_id):
        return self.conn.execute('SELECT option_index FROM poll_votes WHERE poll_id = ? AND member_id = ?',
            (poll_id, member_id)).fetchall()

    def voter_count(self, poll_id):
        return self.conn.execute('SELECT COUNT(DISTINCT member_id) FROM poll_votes WHERE poll_id = ?',
            (poll_id,)).fetchone()[0]

    def list_for_api(self, limit, offset):
        return self.conn.execute('''SELECT p.id, p.question, p.options_json, p.status, p.created_at,
            p.created_by, p.allow_multiple,
            (SELECT COUNT(*) FROM poll_votes pv WHERE pv.poll_id = p.id) AS total_votes
            FROM polls p ORDER BY p.created_at DESC LIMIT ? OFFSET ?''', (limit, offset)).fetchall()

    def create_with_deadline(self, question, options_json, member_id, closes_at, allow_multiple):
        return self.conn.execute("INSERT INTO polls (question, options_json, created_by, status, closes_at, allow_multiple) VALUES (?, ?, ?, 'open', ?, ?)",
            (question, options_json, member_id, closes_at, int(allow_multiple))).lastrowid

    def set_status(self, poll_id, status, closes_at):
        self.conn.execute('UPDATE polls SET status = ?, closes_at = ? WHERE id = ?', (status, closes_at, poll_id))

    def delete_votes(self, poll_id):
        self.conn.execute('DELETE FROM poll_votes WHERE poll_id = ?', (poll_id,))

    def delete(self, poll_id):
        return self.conn.execute('DELETE FROM polls WHERE id = ?', (poll_id,)).rowcount

    def detail_with_creator(self, poll_id):
        return self.conn.execute('SELECT p.*, m.username AS creator FROM polls p JOIN members m ON m.id = p.created_by WHERE p.id = ?', (poll_id,)).fetchone()

    def open_options(self, poll_id):
        return self.conn.execute("SELECT options_json FROM polls WHERE id = ? AND status = 'open'", (poll_id,)).fetchone()

    def list_for_admin(self):
        return self.conn.execute("""
            SELECT p.*, m.username as creator,
                   (SELECT COUNT(*) FROM poll_votes pv WHERE pv.poll_id = p.id) as total_votes
            FROM polls p
            JOIN members m ON m.id = p.created_by
            ORDER BY p.created_at DESC
            LIMIT 50
        """).fetchall()

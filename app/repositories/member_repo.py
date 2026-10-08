class MemberRepository:
    def __init__(self, conn):
        self.conn = conn

    def count(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM members")
        return cur.fetchone()[0]

    def get_by_id(self, member_id):
        return self.conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()

    def get_by_username(self, username):
        return self.conn.execute("SELECT * FROM members WHERE username = ?", (username,)).fetchone()

    def find_login(self, username):
        return self.conn.execute(
            """SELECT * FROM members
               WHERE username = ? OR (email IS NOT NULL AND lower(email) = lower(?))
               ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END LIMIT 1""",
            (username, username, username),
        ).fetchone()

    def set_password_hash(self, member_id, password_hash):
        self.conn.execute("UPDATE members SET password_hash = ? WHERE id = ?", (password_hash, member_id))

    def create(self, username, password_hash, is_admin=0):
        return self.conn.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, is_admin),
        ).lastrowid

    def email_in_use(self, email, member_id):
        return self.conn.execute(
            "SELECT 1 FROM members WHERE lower(email) = lower(?) AND id != ?", (email, member_id)
        ).fetchone() is not None

    def add_email(self, member_id, email):
        self.conn.execute(
            "UPDATE members SET email = ? WHERE id = ? AND (email IS NULL OR trim(email) = '')",
            (email, member_id),
        )

    def find_oidc_identity(self, subject, email):
        member = self.conn.execute("SELECT * FROM members WHERE oidc_sub = ?", (subject,)).fetchone()
        if member is None and email:
            member = self.conn.execute(
                "SELECT * FROM members WHERE oidc_sub IS NULL AND email IS NOT NULL AND lower(email) = lower(?) LIMIT 1",
                (email,),
            ).fetchone()
        return member

    def update_oidc_identity(self, member_id, subject, email, display_name, is_admin,
                             telegram_username, telegram_user_id, linked_at):
        self.conn.execute(
            "UPDATE members SET oidc_sub = ?, email = COALESCE(?, email), display_name = ?, is_admin = ?, telegram_username = COALESCE(?, telegram_username), telegram_user_id = COALESCE(?, telegram_user_id), last_linked_at = COALESCE(?, last_linked_at) WHERE id = ?",
            (subject, email, display_name, is_admin, telegram_username, telegram_user_id, linked_at, member_id),
        )

    def create_oidc_identity(self, username, password_hash, is_admin, telegram_username,
                             telegram_user_id, linked_at, subject, email, display_name):
        return self.conn.execute(
            "INSERT INTO members (username, password_hash, is_admin, telegram_username, telegram_user_id, last_linked_at, oidc_sub, email, display_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (username, password_hash, is_admin, telegram_username, telegram_user_id, linked_at, subject, email, display_name),
        ).lastrowid

    def list_telegram_links(self, include_unlinked, limit, offset):
        from app.repositories.member_queries import LINKED_CONDITION_SQL, link_state_case_sql
        if include_unlinked:
            projection = f"CASE WHEN {LINKED_CONDITION_SQL} THEN 1 ELSE 0 END AS linked, {link_state_case_sql()} AS link_state"
            condition = ''
        else:
            projection = "1 AS linked, 'linked' AS link_state"
            condition = f'WHERE {LINKED_CONDITION_SQL}'
        return self.conn.execute(f'''SELECT id, username, telegram_username, telegram_user_id,
            last_linked_at, last_unlinked_at, {projection} FROM members {condition}
            ORDER BY id ASC LIMIT ? OFFSET ?''', (limit, offset)).fetchall()

    def statistics(self, limit, offset):
        from app.repositories.member_queries import user_statistics_query, user_statistics_total_query
        query, params = user_statistics_query(limit, offset)
        total_query, total_params = user_statistics_total_query()
        rows = self.conn.execute(query, params).fetchall()
        total = int(self.conn.execute(total_query, total_params).fetchone()['total'])
        return rows, total

    def create_with_email(self, username, email, password_hash, is_admin):
        return self.conn.execute('INSERT INTO members (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)',
            (username, email, password_hash, is_admin)).lastrowid

    def identity_in_use(self, member_id, username, email):
        return self.conn.execute('''SELECT 1 FROM members WHERE id != ? AND
            (username = ? OR (? IS NOT NULL AND lower(email) = lower(?)))''',
            (member_id, username, email, email)).fetchone() is not None

    def update_identity(self, member_id, username, email):
        self.conn.execute('UPDATE members SET username = ?, email = ? WHERE id = ?', (username, email, member_id))

    def delete(self, member_id):
        self.conn.execute('DELETE FROM members WHERE id = ?', (member_id,))

    def set_admin(self, member_id, is_admin):
        self.conn.execute('UPDATE members SET is_admin = ? WHERE id = ?', (is_admin, member_id))

    def list_for_admin(self):
        return self.conn.execute('SELECT * FROM members ORDER BY created_at').fetchall()

    def proposal_statistics(self):
        return self.conn.execute("""
            SELECT
                m.id,
                m.username,
                m.email,
                m.is_admin,
                (SELECT COUNT(*) FROM votes v JOIN proposals p ON v.proposal_id = p.id WHERE v.member_id = m.id) as vote_count,
                (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id) as proposal_count,
                (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved') as approved_count,
                (SELECT COUNT(*) FROM comments c JOIN proposals p ON c.proposal_id = p.id WHERE c.member_id = m.id) as comment_count
            FROM members m
            ORDER BY vote_count DESC, proposal_count DESC
        """).fetchall()

    def poll_statistics(self):
        return self.conn.execute("""
            SELECT
                m.id,
                m.username,
                m.email,
                m.is_admin,
                (SELECT COUNT(*) FROM poll_votes pv WHERE pv.member_id = m.id) AS poll_vote_count,
                (SELECT COUNT(*) FROM polls p WHERE p.created_by = m.id) AS poll_created_count
            FROM members m
            ORDER BY poll_vote_count DESC, poll_created_count DESC, m.username ASC
        """).fetchall()

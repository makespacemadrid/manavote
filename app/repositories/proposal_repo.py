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

    def detail_with_creator(self, proposal_id):
        return self.conn.execute(
            "SELECT p.*, m.username AS creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.id = ?",
            (proposal_id,),
        ).fetchone()

    def update_fields(self, proposal_id, title, description, amount, url, basic_supplies, image_filename=None,
                      *, update_image=False):
        if update_image:
            self.conn.execute(
                "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, image_filename = ?, basic_supplies = ? WHERE id = ?",
                (title, description, amount, url, image_filename, basic_supplies, proposal_id),
            )
        else:
            self.conn.execute(
                "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, basic_supplies = ? WHERE id = ?",
                (title, description, amount, url, basic_supplies, proposal_id),
            )

    def set_basic_supplies(self, proposal_id, basic_supplies):
        self.conn.execute("UPDATE proposals SET basic_supplies = ? WHERE id = ?", (basic_supplies, proposal_id))

    def api_details(self, proposal_id):
        return self.conn.execute(
            "SELECT id, title, description, amount, url, created_by, status, created_at, basic_supplies FROM proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()

    def list_for_api(self, *, status, age, cutoff, limit, offset):
        params, conditions = [], []
        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if age:
            if not status:
                conditions.append("p.status = 'active'")
            comparator = ">" if age == "recent" else "<="
            conditions.append(f"datetime(p.created_at) {comparator} datetime(?)")
            params.append(cutoff)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return self.conn.execute(
            """SELECT p.id, p.title, p.description, p.amount, p.url, p.created_by, p.status, p.created_at, p.basic_supplies,
                      COALESCE(SUM(CASE WHEN v.vote = 'in_favor' THEN 1 ELSE 0 END), 0) AS yes_votes,
                      COALESCE(SUM(CASE WHEN v.vote = 'against' THEN 1 ELSE 0 END), 0) AS no_votes
               FROM proposals p LEFT JOIN votes v ON v.proposal_id = p.id""" + where +
            " GROUP BY p.id ORDER BY p.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()

    def set_purchased_at(self, proposal_id, purchased_at):
        self.conn.execute(
            "UPDATE proposals SET purchased_at = ? WHERE id = ?", (purchased_at, proposal_id)
        )

    def reset_approval(self, proposal_id):
        self.conn.execute(
            "UPDATE proposals SET status = 'active', processed_at = NULL, purchased_at = NULL WHERE id = ?",
            (proposal_id,),
        )

    def delete(self, proposal_id):
        self.conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]

    def list_for_page(self, filter_type, old_cutoff):
        conditions = {
            "basic": ("p.basic_supplies = 1", ()),
            "old": ("p.status = 'active' AND datetime(p.created_at) <= datetime(?)", (old_cutoff,)),
            "recent": ("p.status = 'active' AND datetime(p.created_at) > datetime(?)", (old_cutoff,)),
            "purchased": ("p.purchased_at IS NOT NULL", ()),
            "not_purchased": ("p.status = 'approved' AND p.purchased_at IS NULL", ()),
            "expensive": ("p.amount > 50 AND p.status IN ('active', 'approved')", ()),
            "standard": ("p.status = 'approved' AND p.basic_supplies = 0 AND p.amount <= 50", ()),
        }
        if filter_type in {"active", "approved", "over_budget"}:
            condition, params = "p.status = ?", (filter_type,)
        else:
            condition, params = conditions.get(filter_type, ("1 = 1", ()))
        return self.conn.execute(
            "SELECT p.*, m.username AS creator FROM proposals p "
            "JOIN members m ON p.created_by = m.id "
            f"WHERE {condition} ORDER BY p.created_at DESC",
            params,
        ).fetchall()

    def page_totals(self, old_cutoff):
        # Keep the existing chip predicates: expensive totals include every status,
        # while the expensive list intentionally includes active/approved only.
        conditions = {
            "active_proposals_sum": ("status = 'active'", ()),
            "old_proposals_sum": ("status = 'active' AND datetime(created_at) <= datetime(?)", (old_cutoff,)),
            "recent_proposals_sum": ("status = 'active' AND datetime(created_at) > datetime(?)", (old_cutoff,)),
            "committed": ("status = 'over_budget'", ()),
            "pending_purchase_sum": ("status = 'approved' AND purchased_at IS NULL", ()),
            "purchased_sum": ("purchased_at IS NOT NULL", ()),
            "approved_sum": ("status = 'approved'", ()),
            "basic_sum": ("basic_supplies = 1", ()),
            "standard_sum": ("status = 'approved' AND basic_supplies = 0 AND amount <= 50", ()),
            "expensive_sum": ("amount > 50", ()),
            "all_sum": ("1 = 1", ()),
        }
        return {
            name: self.conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM proposals WHERE {condition}", params
            ).fetchone()[0]
            for name, (condition, params) in conditions.items()
        }

    def amounts_by_day(self):
        queries = {
            "pending": "SELECT date(over_budget_at), COALESCE(SUM(amount), 0) FROM proposals WHERE over_budget_at IS NOT NULL GROUP BY date(over_budget_at)",
            "approved": "SELECT date(processed_at), COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL GROUP BY date(processed_at)",
            "approved_from_pending": "SELECT date(processed_at), COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL AND over_budget_at IS NOT NULL GROUP BY date(processed_at)",
            "proposals": "SELECT date(created_at), COALESCE(SUM(amount), 0) FROM proposals GROUP BY date(created_at)",
        }
        return {
            name: {row[0]: row[1] for row in self.conn.execute(query).fetchall()}
            for name, query in queries.items()
        }

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

    def history_events(self):
        return self.conn.execute("""
            SELECT * FROM (
                SELECT
                    p.created_at as event_at,
                    'proposal_added' as event_type,
                    m.username as actor,
                    p.id as proposal_id,
                    p.title as proposal_title,
                    NULL as vote_value
                FROM proposals p
                JOIN members m ON m.id = p.created_by

                UNION ALL

                SELECT
                    v.created_at as event_at,
                    'member_voted' as event_type,
                    m.username as actor,
                    p.id as proposal_id,
                    p.title as proposal_title,
                    v.vote as vote_value
                FROM votes v
                JOIN members m ON m.id = v.member_id
                JOIN proposals p ON p.id = v.proposal_id

                UNION ALL

                SELECT
                    p.processed_at as event_at,
                    'proposal_approved' as event_type,
                    NULL as actor,
                    p.id as proposal_id,
                    p.title as proposal_title,
                    NULL as vote_value
                FROM proposals p
                WHERE p.status = 'approved' AND p.processed_at IS NOT NULL
            )
            WHERE event_at IS NOT NULL
            ORDER BY event_at DESC
            LIMIT 300
        """).fetchall()

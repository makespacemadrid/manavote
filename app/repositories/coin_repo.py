"""Persistence for the Coins inventory and member ledger."""


class CoinRepository:
    def __init__(self, connection):
        self.connection = connection

    def find_item(self, item):
        if isinstance(item, str) and item.strip().isdigit():
            item = int(item.strip())
        if isinstance(item, int) and not isinstance(item, bool):
            return self.connection.execute(
                "SELECT * FROM coin_items WHERE id = ? AND active = 1", (item,)
            ).fetchone()
        return self.connection.execute(
            "SELECT * FROM coin_items WHERE name = ? COLLATE NOCASE AND active = 1",
            (str(item).strip(),),
        ).fetchone()

    def insert_item(self, name, pack_size):
        cursor = self.connection.execute(
            """INSERT INTO coin_items (name, position, pack_size)
               VALUES (?, COALESCE((SELECT MAX(position) + 1 FROM coin_items), 0), ?)""",
            (name, pack_size),
        )
        return cursor.lastrowid

    def list_items(self, member_id=None):
        return self.connection.execute(
            """SELECT i.*, COALESCE(SUM(m.inventory_delta), 0) AS stock,
                      COALESCE(SUM(CASE WHEN m.member_id = ? THEN m.coin_delta ELSE 0 END), 0) AS member_balance
               FROM coin_items i LEFT JOIN coin_movements m ON m.item_id = i.id
               WHERE i.active = 1 GROUP BY i.id ORDER BY i.position, i.id""",
            (member_id,),
        ).fetchall()

    def member_balance(self, member_id):
        row = self.connection.execute(
            "SELECT COALESCE(SUM(coin_delta), 0) AS balance FROM coin_movements WHERE member_id = ?",
            (member_id,),
        ).fetchone()
        return int(row["balance"])

    def member_rankings(self):
        """Return every member's coin balance and lifetime purchase/consumption totals."""
        return self.connection.execute(
            """SELECT m.id, m.username,
                      COALESCE(SUM(cm.coin_delta), 0) AS balance,
                      COALESCE(SUM(CASE WHEN cm.kind = 'consume'
                                        THEN -cm.coin_delta ELSE 0 END), 0) AS total_consumed,
                      COALESCE(SUM(CASE WHEN cm.kind = 'replenish'
                                        THEN cm.coin_delta ELSE 0 END), 0) AS total_bought
               FROM members m
               LEFT JOIN coin_movements cm ON cm.member_id = m.id
               GROUP BY m.id
               ORDER BY balance DESC, m.username COLLATE NOCASE, m.id"""
        ).fetchall()

    def recent_movements(self, limit=30, offset=0, *, member_id=None, item_id=None):
        conditions = []
        params = []
        if member_id is not None:
            conditions.append("cm.member_id = ?")
            params.append(member_id)
        if item_id is not None:
            conditions.append("cm.item_id = ?")
            params.append(item_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return self.connection.execute(
            """SELECT cm.*, ci.name AS item_name, m.username
               FROM coin_movements cm JOIN coin_items ci ON ci.id = cm.item_id
               JOIN members m ON m.id = cm.member_id
            """ + where + " ORDER BY cm.id DESC LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        ).fetchall()

    def movement_by_key(self, key):
        return self.connection.execute(
            "SELECT * FROM coin_movements WHERE idempotency_key = ?", (key,)
        ).fetchone()

    def insert_movement(self, item_id, member_id, delta, kind, source, key):
        cursor = self.connection.execute(
            """INSERT INTO coin_movements
               (item_id, member_id, inventory_delta, coin_delta, kind, source, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item_id, member_id, delta, delta, kind, source, key),
        )
        return cursor.lastrowid

    def insert_adjustment(self, item_id, member_id, inventory_delta, key, note=None):
        cursor = self.connection.execute(
            """INSERT INTO coin_movements
               (item_id, member_id, inventory_delta, coin_delta, kind, source, idempotency_key, note)
               VALUES (?, ?, ?, 0, 'adjustment', 'admin', ?, ?)""",
            (item_id, member_id, inventory_delta, key, note),
        )
        return cursor.lastrowid

    def item_stock(self, item_id):
        row = self.connection.execute(
            "SELECT COALESCE(SUM(inventory_delta), 0) AS stock FROM coin_movements WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        return int(row["stock"])

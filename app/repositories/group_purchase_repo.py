"""Persistence for purchases, selections, shared costs, and payments."""


class GroupPurchaseRepository:
    def __init__(self, connection):
        self.conn = connection

    def get_by_id(self, purchase_id):
        return self.conn.execute('SELECT * FROM group_purchases WHERE id = ?', (purchase_id,)).fetchone()

    def list_with_creators(self):
        return self.conn.execute('''SELECT gp.*, m.username AS creator FROM group_purchases gp
            JOIN members m ON m.id = gp.created_by ORDER BY gp.created_at DESC, gp.id DESC''').fetchall()

    def components(self, purchase_id):
        return self.conn.execute('SELECT * FROM group_purchase_components WHERE group_purchase_id = ? ORDER BY position, id', (purchase_id,)).fetchall()

    def component_totals(self, purchase_id):
        return self.conn.execute('''SELECT c.id, c.name, c.unit_price, COALESCE(SUM(q.quantity), 0) AS total_quantity
            FROM group_purchase_components c LEFT JOIN group_purchase_quantities q ON q.component_id = c.id
            WHERE c.group_purchase_id = ? GROUP BY c.id, c.name, c.position ORDER BY c.position, c.id''', (purchase_id,)).fetchall()

    def orders(self, component_id):
        return self.conn.execute('''SELECT q.quantity, q.member_id, m.username FROM group_purchase_quantities q
            JOIN members m ON m.id = q.member_id WHERE q.component_id = ? AND q.quantity > 0
            ORDER BY m.username COLLATE NOCASE''', (component_id,)).fetchall()

    def shared_costs(self, purchase_id):
        return self.conn.execute('SELECT * FROM group_purchase_shared_costs WHERE group_purchase_id = ? ORDER BY position, id', (purchase_id,)).fetchall()

    def debts(self, purchase_id):
        return self.conn.execute('''SELECT m.id AS member_id, m.username,
            SUM(q.quantity * c.unit_price) AS selection_amount, pp.received_at
            FROM group_purchase_quantities q JOIN group_purchase_components c ON c.id = q.component_id
            JOIN members m ON m.id = q.member_id LEFT JOIN group_purchase_payments pp
            ON pp.group_purchase_id = c.group_purchase_id AND pp.member_id = m.id
            WHERE c.group_purchase_id = ? AND q.quantity > 0 GROUP BY m.id, m.username, pp.received_at
            ORDER BY m.username COLLATE NOCASE''', (purchase_id,)).fetchall()

    def create(self, title, description, deadline, url, image_filename, payment_method, member_id):
        return self.conn.execute('''INSERT INTO group_purchases
            (title, description, deadline, url, image_filename, payment_method, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (title, description, deadline or None, url or None, image_filename, payment_method or None, member_id)).lastrowid

    def insert_components(self, purchase_id, components):
        self.conn.executemany('INSERT INTO group_purchase_components (group_purchase_id, name, unit_price, position) VALUES (?, ?, ?, ?)',
            [(purchase_id, name, price, position) for position, (name, price) in enumerate(components)])

    def insert_shared_costs(self, purchase_id, shared_costs):
        self.conn.executemany('INSERT INTO group_purchase_shared_costs (group_purchase_id, label, amount, position) VALUES (?, ?, ?, ?)',
            [(purchase_id, label, amount, position) for position, (label, amount) in enumerate(shared_costs)])

    def update(self, purchase_id, title, description, deadline, url, image_filename, payment_method):
        self.conn.execute('''UPDATE group_purchases SET title = ?, description = ?, deadline = ?, url = ?, image_filename = ?, payment_method = ? WHERE id = ?''',
            (title, description, deadline or None, url or None, image_filename, payment_method or None, purchase_id))

    def update_components(self, updates):
        self.conn.executemany('UPDATE group_purchase_components SET name = ?, unit_price = ? WHERE id = ? AND group_purchase_id = ?', updates)

    def delete_shared_costs(self, purchase_id):
        self.conn.execute('DELETE FROM group_purchase_shared_costs WHERE group_purchase_id = ?', (purchase_id,))

    def open_component(self, purchase_id, component_id):
        return self.conn.execute('''SELECT c.id FROM group_purchase_components c
            JOIN group_purchases gp ON gp.id = c.group_purchase_id
            WHERE c.id = ? AND gp.id = ? AND gp.status = 'open' ''', (component_id, purchase_id)).fetchone()

    def set_quantity(self, component_id, member_id, quantity):
        if quantity == 0:
            self.conn.execute('DELETE FROM group_purchase_quantities WHERE component_id = ? AND member_id = ?', (component_id, member_id))
        else:
            self.conn.execute('''INSERT INTO group_purchase_quantities (component_id, member_id, quantity, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(component_id, member_id) DO UPDATE SET
                quantity = excluded.quantity, updated_at = CURRENT_TIMESTAMP''', (component_id, member_id, quantity))

    def delete(self, purchase_id):
        self.conn.execute('''DELETE FROM group_purchase_quantities WHERE component_id IN
            (SELECT id FROM group_purchase_components WHERE group_purchase_id = ?)''', (purchase_id,))
        self.conn.execute('DELETE FROM group_purchase_payments WHERE group_purchase_id = ?', (purchase_id,))
        self.delete_shared_costs(purchase_id)
        self.conn.execute('DELETE FROM group_purchase_components WHERE group_purchase_id = ?', (purchase_id,))
        self.conn.execute('DELETE FROM group_purchases WHERE id = ?', (purchase_id,))

    def set_status(self, purchase_id, status):
        self.conn.execute('UPDATE group_purchases SET status = ? WHERE id = ?', (status, purchase_id))

    def is_participant(self, purchase_id, member_id):
        return self.conn.execute('''SELECT 1 FROM group_purchase_quantities q
            JOIN group_purchase_components c ON c.id = q.component_id
            WHERE c.group_purchase_id = ? AND q.member_id = ? AND q.quantity > 0 LIMIT 1''', (purchase_id, member_id)).fetchone() is not None

    def set_payment(self, purchase_id, member_id, received):
        if received:
            self.conn.execute('INSERT OR REPLACE INTO group_purchase_payments (group_purchase_id, member_id) VALUES (?, ?)', (purchase_id, member_id))
        else:
            self.conn.execute('DELETE FROM group_purchase_payments WHERE group_purchase_id = ? AND member_id = ?', (purchase_id, member_id))

    def list_for_admin(self):
        return self.conn.execute("""
            SELECT gp.id, gp.title, gp.status, gp.created_at, m.username AS creator
            FROM group_purchases gp
            JOIN members m ON m.id = gp.created_by
            ORDER BY gp.created_at DESC, gp.id DESC
        """).fetchall()

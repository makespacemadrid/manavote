"""Explicit copy fields; participation and lifecycle history never follow a copy."""
class CopyRepository:
    TABLES = {'proposal': 'proposals', 'poll': 'polls', 'group_purchase': 'group_purchases'}

    def __init__(self, conn):
        self.conn = conn

    def source(self, kind, source_id):
        return self.conn.execute(f'SELECT * FROM {self.TABLES[kind]} WHERE id=?', (source_id,)).fetchone()

    def member_exists(self, member_id):
        return self.conn.execute('SELECT 1 FROM members WHERE id=?', (member_id,)).fetchone() is not None

    def prior_request(self, creator, key):
        return self.conn.execute('SELECT fingerprint,result_json FROM copy_requests WHERE creator_id=? AND request_key=?', (creator, key)).fetchone()

    def save_request(self, creator, key, fingerprint, result):
        self.conn.execute('INSERT INTO copy_requests(creator_id,request_key,fingerprint,result_json) VALUES (?,?,?,?)', (creator, key, fingerprint, result))

    def proposal(self, source, creator, title, image, deadline=None):
        item_id = self.conn.execute('''INSERT INTO proposals(title,description,amount,url,image_filename,created_by,basic_supplies,status)
            VALUES (?,?,?,?,?,?,?,'active')''', (title, source['description'], source['amount'], source['url'], image, creator,
            int(bool(source['basic_supplies']) and source['amount'] <= 20))).lastrowid
        if deadline:
            self.conn.execute('UPDATE proposals SET voting_deadline=? WHERE id=?', (deadline,item_id))
        return item_id

    def poll(self, source, creator, question, closes_at):
        return self.conn.execute("INSERT INTO polls(question,options_json,created_by,allow_multiple,closes_at,status) VALUES (?,?,?,?,?,'open')",
            (question, source['options_json'], creator, source['allow_multiple'], closes_at)).lastrowid

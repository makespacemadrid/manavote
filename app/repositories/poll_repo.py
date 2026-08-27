import json


class PollRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, question, options, created_by):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO polls (question, options_json, created_by, status) VALUES (?, ?, ?, 'open')",
            (question, json.dumps(options), created_by),
        )
        self.conn.commit()
        return cur.lastrowid

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

class SettingsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_value(self, key, default=None):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_value(self, key, value):
        cur = self.conn.cursor()
        cur.execute("UPDATE settings SET value = ? WHERE key = ?", (str(value), key))

    def get_thresholds(self):
        cur = self.conn.cursor()
        cur.execute("SELECT key, value FROM settings WHERE key LIKE 'threshold_%'")
        thresholds = {row[0]: float(row[1]) for row in cur.fetchall()}
        return {
            "basic": thresholds.get("threshold_basic", 5),
            "over50": thresholds.get("threshold_over50", 20),
            "default": thresholds.get("threshold_default", 10),
        }

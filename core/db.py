import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def init(self):
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS vps (
                name TEXT PRIMARY KEY, discord_id INTEGER NOT NULL,
                ram_mb INTEGER NOT NULL, cpu_percent INTEGER NOT NULL,
                disk_mb INTEGER NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, expires_at TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_vps_owner ON vps(discord_id)')

    def add(self, name, uid, ram, cpu, disk, days):
        now = datetime.now(timezone.utc)
        with self.connect() as db:
            db.execute('INSERT INTO vps VALUES (?,?,?,?,?,?,?,?)',
                (name, uid, ram, cpu, disk, 'running', now.isoformat(),
                 (now + timedelta(days=days)).isoformat()))

    def get(self, name):
        with self.connect() as db:
            return db.execute('SELECT * FROM vps WHERE name=?', (name,)).fetchone()

    def user(self, uid):
        with self.connect() as db:
            return db.execute('SELECT * FROM vps WHERE discord_id=? ORDER BY created_at DESC', (uid,)).fetchall()

    def all(self):
        with self.connect() as db:
            return db.execute('SELECT * FROM vps ORDER BY created_at DESC').fetchall()

    def status(self, name, value):
        with self.connect() as db:
            db.execute('UPDATE vps SET status=? WHERE name=?', (value, name))

    def delete(self, name):
        with self.connect() as db:
            db.execute('DELETE FROM vps WHERE name=?', (name,))

    def expired(self):
        with self.connect() as db:
            return db.execute('SELECT * FROM vps WHERE expires_at<=?', (datetime.now(timezone.utc).isoformat(),)).fetchall()

    def extend(self, uid, days, reset=False):
        now = datetime.now(timezone.utc)
        with self.connect() as db:
            rows = db.execute('SELECT name,expires_at FROM vps WHERE discord_id=?', (uid,)).fetchall()
            for row in rows:
                old = datetime.fromisoformat(row['expires_at'])
                base = now if reset or old < now else old
                db.execute('UPDATE vps SET expires_at=? WHERE name=?', ((base + timedelta(days=days)).isoformat(), row['name']))
            return len(rows)

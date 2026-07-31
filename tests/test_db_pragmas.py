"""SQLite connection pragma checks (WAL, foreign_keys)."""

from portfolio.db import get_db


def test_wal_and_foreign_keys_enabled(app_ctx):
    db = get_db()
    journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]
    busy_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout >= 5000

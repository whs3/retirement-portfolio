"""SQLite connection helpers and schema initialization."""

import sqlite3

from flask import current_app, g

# Applied on every connection for durability and referential integrity.
_CONNECTION_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)


def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    for pragma in _CONNECTION_PRAGMAS:
        conn.execute(pragma)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        _apply_connection_pragmas(g.db)
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(database_path: str | None = None):
    """Create tables and apply lightweight migrations.

    When called outside an app context, pass ``database_path`` explicitly
    (used by seed.py). Inside the app, the path is taken from config.
    """
    if database_path is None:
        database_path = current_app.config["DATABASE"]

    conn = sqlite3.connect(database_path)
    _apply_connection_pragmas(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            ticker        TEXT    NOT NULL DEFAULT '',
            asset_type    TEXT    NOT NULL,
            category      TEXT    NOT NULL DEFAULT '',
            shares        REAL    NOT NULL DEFAULT 0,
            cost_basis    REAL    NOT NULL DEFAULT 0,
            current_value REAL    NOT NULL DEFAULT 0,
            purchase_date TEXT    NOT NULL DEFAULT '',
            notes         TEXT    NOT NULL DEFAULT '',
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS target_allocations (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            category           TEXT    NOT NULL UNIQUE,
            target_percentage  REAL    NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    # Migrate existing databases: add columns if missing
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN account_type TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migrate target_allocations: rename asset_type → category if needed
    cols = [row[1] for row in conn.execute("PRAGMA table_info(target_allocations)")]
    if "asset_type" in cols and "category" not in cols:
        conn.execute("ALTER TABLE target_allocations RENAME COLUMN asset_type TO category")
        conn.commit()
    # Settings table (key-value store for user configuration)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()

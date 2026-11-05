"""SQLite connection helpers and schema initialization."""

import sqlite3
from contextlib import closing

from flask import current_app, g

# Applied on every connection for durability and referential integrity.
_CONNECTION_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)

_SCHEMA = """
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

-- Key-value store for user configuration.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- Daily portfolio value snapshots (one row per calendar date; upserted).
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    date             TEXT PRIMARY KEY,
    total_value      REAL NOT NULL,
    total_cost_basis REAL NOT NULL,
    category_json    TEXT NOT NULL,
    holdings_json    TEXT NOT NULL,
    untracked_value  REAL NOT NULL,
    created_at       TEXT NOT NULL,
    owner_accounts_json TEXT
);

-- External deposits and withdrawals. Investment return is the change in
-- portfolio value minus these amounts, so a deposit is not a gain.
CREATE TABLE IF NOT EXISTS cash_flows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_date     TEXT    NOT NULL,
    amount        REAL    NOT NULL,
    owner         TEXT    NOT NULL DEFAULT '',
    account_type  TEXT    NOT NULL DEFAULT '',
    ticker        TEXT    NOT NULL DEFAULT '',
    note          TEXT    NOT NULL DEFAULT '',
    source        TEXT    NOT NULL DEFAULT 'manual',
    holding_id    INTEGER,
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cash_flows_date ON cash_flows(flow_date);
"""

# Columns added after a table was first released: (table, column, definition).
# owner/account_type are never in CREATE TABLE, so new databases get them here too.
# For portfolio_snapshots.owner_accounts_json, NULL means that day's row has no
# breakdown; an empty object means it was captured and every balance was zero.
_ADDED_COLUMNS = (
    ("holdings", "category", "TEXT NOT NULL DEFAULT ''"),
    ("holdings", "owner", "TEXT NOT NULL DEFAULT ''"),
    ("holdings", "account_type", "TEXT NOT NULL DEFAULT ''"),
    ("portfolio_snapshots", "owner_accounts_json", "TEXT"),
)


def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    for pragma in _CONNECTION_PRAGMAS:
        conn.execute(pragma)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, definition in _ADDED_COLUMNS:
        if column not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    # target_allocations was originally keyed by asset_type.
    alloc_cols = _columns(conn, "target_allocations")
    if "asset_type" in alloc_cols and "category" not in alloc_cols:
        conn.execute("ALTER TABLE target_allocations RENAME COLUMN asset_type TO category")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=30)
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

    with closing(sqlite3.connect(database_path)) as conn:
        _apply_connection_pragmas(conn)
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()

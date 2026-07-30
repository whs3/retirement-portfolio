"""App settings helpers (key-value store in SQLite)."""

from portfolio.db import get_db

ALLOWED_SETTINGS = {"fmp_api_key"}


def get_fmp_api_key() -> str:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key='fmp_api_key'"
    ).fetchone()
    return row["value"] if row else ""

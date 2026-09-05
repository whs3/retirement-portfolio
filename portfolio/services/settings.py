"""App settings helpers (key-value store in SQLite)."""

import math

from portfolio.db import get_db

PRICE_REFRESH_KEY = "price_refresh_minutes"
DEFAULT_PRICE_REFRESH_MINUTES = 15
MAX_PRICE_REFRESH_MINUTES = 1440  # 24 hours

ALLOWED_SETTINGS = {"fmp_api_key", PRICE_REFRESH_KEY}


def get_fmp_api_key() -> str:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key='fmp_api_key'"
    ).fetchone()
    return row["value"] if row else ""


def parse_price_refresh_minutes(value) -> int:
    """Return a whole-minute interval. 0 means auto-refresh is off."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Refresh interval must be a number of minutes")
    if isinstance(value, str):
        value = value.strip()
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        raise ValueError("Refresh interval must be a number of minutes") from None
    if math.isnan(as_float) or math.isinf(as_float):
        raise ValueError("Refresh interval must be a number of minutes")
    minutes = int(as_float)
    if as_float != minutes:
        raise ValueError("Refresh interval must be a whole number of minutes")
    if minutes < 0:
        raise ValueError("Refresh interval cannot be negative")
    if minutes > MAX_PRICE_REFRESH_MINUTES:
        raise ValueError(
            f"Refresh interval cannot exceed {MAX_PRICE_REFRESH_MINUTES} minutes"
        )
    return minutes


def get_price_refresh_minutes() -> int:
    """Stored interval, or the 15-minute default when unset/invalid."""
    row = get_db().execute(
        "SELECT value FROM settings WHERE key=?", (PRICE_REFRESH_KEY,)
    ).fetchone()
    if not row:
        return DEFAULT_PRICE_REFRESH_MINUTES
    try:
        return parse_price_refresh_minutes(row["value"])
    except ValueError:
        return DEFAULT_PRICE_REFRESH_MINUTES

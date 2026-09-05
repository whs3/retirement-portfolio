"""App settings helpers (key-value store in SQLite)."""

import math
from datetime import date, datetime

from portfolio.db import get_db
from portfolio.services.withdrawal import MAX_YEARS

PRICE_REFRESH_KEY = "price_refresh_minutes"
DEFAULT_PRICE_REFRESH_MINUTES = 15
MAX_PRICE_REFRESH_MINUTES = 1440  # 24 hours

# Owners are a fixed set hardcoded throughout the UI (Akiko/Bill/Joint); only
# the two individual owners can hold a birthdate for RMD purposes.
BIRTHDATE_KEYS = {"birthdate_bill", "birthdate_akiko"}

WITHDRAWAL_RATE_KEYS = {
    "withdrawal_rate",
    "withdrawal_return_rate",
    "withdrawal_inflation_rate",
}
WITHDRAWAL_YEARS_KEY = "withdrawal_years"

ALLOWED_SETTINGS = (
    {"fmp_api_key", PRICE_REFRESH_KEY}
    | BIRTHDATE_KEYS
    | WITHDRAWAL_RATE_KEYS
    | {WITHDRAWAL_YEARS_KEY}
)

_MIN_BIRTH_YEAR = 1900


def parse_birthdate(value) -> str:
    """Validate a YYYY-MM-DD birthdate string. Empty string clears the setting."""
    if not isinstance(value, str):
        raise ValueError("Birthdate must be a string in YYYY-MM-DD format")
    value = value.strip()
    if value == "":
        return value
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Birthdate must be in YYYY-MM-DD format") from None
    if parsed > date.today():
        raise ValueError("Birthdate cannot be in the future")
    if parsed.year < _MIN_BIRTH_YEAR:
        raise ValueError(f"Birthdate year must be {_MIN_BIRTH_YEAR} or later")
    return value


def parse_withdrawal_rate(value, field_name: str) -> str:
    """Percentage input (rate/return/inflation): 0-50, stored as a string."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number") from None
    if math.isnan(n) or math.isinf(n):
        raise ValueError(f"{field_name} is not a valid number")
    if n < 0 or n > 50:
        raise ValueError(f"{field_name} must be between 0 and 50")
    return str(n)


def parse_withdrawal_years(value) -> str:
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        raise ValueError("Projection years must be a number") from None
    if math.isnan(as_float) or math.isinf(as_float):
        raise ValueError("Projection years must be a number")
    years = int(as_float)
    if as_float != years:
        raise ValueError("Projection years must be a whole number")
    if years < 1 or years > MAX_YEARS:
        raise ValueError(f"Projection years must be between 1 and {MAX_YEARS}")
    return str(years)


def get_fmp_api_key() -> str:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key='fmp_api_key'"
    ).fetchone()
    return row["value"] if row else ""


def get_owner_birthdates() -> dict[str, str | None]:
    """{"Bill": "1960-01-01" or None, "Akiko": ...}."""
    rows = get_db().execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?)",
        tuple(BIRTHDATE_KEYS),
    ).fetchall()
    by_key = {r["key"]: r["value"] for r in rows if r["value"]}
    return {
        "Bill": by_key.get("birthdate_bill"),
        "Akiko": by_key.get("birthdate_akiko"),
    }


def get_withdrawal_assumptions() -> dict:
    """Persisted calculator inputs, with sensible defaults when unset."""
    rows = get_db().execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?, ?, ?)",
        (*WITHDRAWAL_RATE_KEYS, WITHDRAWAL_YEARS_KEY),
    ).fetchall()
    by_key = {r["key"]: r["value"] for r in rows}
    return {
        "withdrawal_rate": float(by_key.get("withdrawal_rate", 4)),
        "withdrawal_return_rate": float(by_key.get("withdrawal_return_rate", 6)),
        "withdrawal_inflation_rate": float(by_key.get("withdrawal_inflation_rate", 3)),
        "withdrawal_years": int(by_key.get(WITHDRAWAL_YEARS_KEY, 30)),
    }


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

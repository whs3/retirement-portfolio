"""Required Minimum Distribution (RMD) estimation.

Estimates only. Uses the IRS Uniform Lifetime Table. The Joint and Last
Survivor table applies when a spouse is the sole beneficiary and more than
10 years younger; this estimate keeps the Uniform Lifetime Table for everyone.

The balance for a calendar year is the prior December 31 snapshot when that
row has an owner and account breakdown. Otherwise the current tax-deferred
balance stands in, which covers years before those snapshots existed.
Age for the table is the age reached on December 31 of the distribution year.
"""

from __future__ import annotations

import json
from datetime import date

# Account types treated as pre-tax / RMD-subject. The app does not currently
# distinguish Traditional vs. Roth 401k/403b by name, so any 401k/403b/IRA/
# Rollover IRA is assumed Traditional; "Roth IRA" and taxable accounts
# (Broker, Cash Management) are excluded.
RMD_SUBJECT_ACCOUNT_TYPES = {"401k", "403b", "IRA", "Rollover IRA"}

# IRS Uniform Lifetime Table (distribution periods), ages 72-120.
UNIFORM_LIFETIME_TABLE: dict[int, float] = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0,
    79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0,
    86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8,
    93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8,
    100: 6.4, 101: 6.0, 102: 5.6, 103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3,
    107: 4.1, 108: 3.9, 109: 3.7, 110: 3.5, 111: 3.4, 112: 3.3, 113: 3.1,
    114: 3.0, 115: 2.9, 116: 2.8, 117: 2.7, 118: 2.5, 119: 2.3, 120: 2.0,
}
_MAX_TABLE_AGE = max(UNIFORM_LIFETIME_TABLE)


def rmd_start_age(birth_year: int) -> int:
    """RMD starting age under SECURE 2.0: 73 for those born 1951-1959,
    75 for 1960 or later (72 for anyone born before 1951, already required)."""
    if birth_year >= 1960:
        return 75
    if birth_year >= 1951:
        return 73
    return 72


def calculate_age(birthdate: date, as_of: date) -> int:
    age = as_of.year - birthdate.year
    if (as_of.month, as_of.day) < (birthdate.month, birthdate.day):
        age -= 1
    return age


def calculate_rmd(birthdate: date, balance: float, as_of: date | None = None) -> dict:
    """Return an RMD estimate for one owner as of ``as_of``.

    Pass December 31 of the distribution year so the age matches the Uniform
    Lifetime Table. ``balance`` is the prior-year-end tax-deferred balance
    when a snapshot has it, and the current balance otherwise.
    """
    as_of = as_of or date.today()
    age = calculate_age(birthdate, as_of)
    start_age = rmd_start_age(birthdate.year)
    required = age >= start_age

    distribution_period = None
    rmd_amount = 0.0
    if required and balance > 0:
        table_age = min(max(age, min(UNIFORM_LIFETIME_TABLE)), _MAX_TABLE_AGE)
        distribution_period = UNIFORM_LIFETIME_TABLE[table_age]
        rmd_amount = round(balance / distribution_period, 2)

    return {
        "age": age,
        "rmd_start_age": start_age,
        "required": required,
        "years_until_required": max(0, start_age - age),
        "distribution_period": distribution_period,
        "balance": round(balance, 2),
        "rmd_amount": rmd_amount,
    }


def project_rmds(
    birthdate: date,
    balance: float,
    return_rate_pct: float,
    years: int,
    as_of: date | None = None,
) -> list[dict]:
    """Year-by-year forward RMD projection for one owner.

    Deterministic, same style as the withdrawal projector: each year's RMD
    (if required) comes out of the balance first, then the remainder grows
    at ``return_rate_pct`` for the year. Age used for the distribution
    period is the age reached by Dec 31 of that calendar year, matching how
    the IRS determines the applicable Uniform Lifetime Table entry.
    """
    as_of = as_of or date.today()
    rows = []
    for i in range(years):
        calendar_year = as_of.year + i
        info = calculate_rmd(birthdate, balance, as_of=date(calendar_year, 12, 31))
        rows.append({
            "year": i + 1,
            "calendar_year": calendar_year,
            "age": info["age"],
            "required": info["required"],
            "distribution_period": info["distribution_period"],
            "balance": round(balance, 2),
            "rmd_amount": info["rmd_amount"],
        })
        balance = max(0.0, balance - info["rmd_amount"]) * (1 + return_rate_pct / 100)
    return rows


def _rmd_balance_for_owner(owner_accounts: dict, owner: str) -> float:
    accounts = owner_accounts.get(owner) or {}
    if not isinstance(accounts, dict):
        return 0.0
    total = sum(
        float(value or 0)
        for account_type, value in accounts.items()
        if account_type in RMD_SUBJECT_ACCOUNT_TYPES
    )
    return round(total, 2)


def _current_rmd_balances(db) -> dict[str, float]:
    placeholders = ",".join("?" * len(RMD_SUBJECT_ACCOUNT_TYPES))
    rows = db.execute(
        f"""SELECT owner, SUM(current_value) AS balance
            FROM holdings
            WHERE owner IN ('Bill', 'Akiko') AND account_type IN ({placeholders})
            GROUP BY owner""",
        tuple(RMD_SUBJECT_ACCOUNT_TYPES),
    ).fetchall()
    found = {r["owner"]: round(r["balance"] or 0.0, 2) for r in rows}
    return {owner: found.get(owner, 0.0) for owner in ("Bill", "Akiko")}


def resolve_rmd_balances(db, as_of: date) -> dict:
    """Prior-year-end tax-deferred balances for Bill and Akiko.

    ``source`` is ``snapshot`` when ``{year-1}-12-31`` has an owner/account
    breakdown (including an empty one). Otherwise ``source`` is ``current``
    and today's balances are used.
    """
    prior = date(as_of.year - 1, 12, 31).isoformat()
    row = db.execute(
        "SELECT owner_accounts_json FROM portfolio_snapshots WHERE date = ?",
        (prior,),
    ).fetchone()

    parsed = None
    if row is not None and row["owner_accounts_json"]:
        try:
            loaded = json.loads(row["owner_accounts_json"])
        except (TypeError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            parsed = loaded

    if parsed is not None:
        return {
            "source": "snapshot",
            "as_of": prior,
            "note": (
                f"{as_of.year} required distributions use the {prior} snapshot."
            ),
            "balances": {
                owner: _rmd_balance_for_owner(parsed, owner)
                for owner in ("Bill", "Akiko")
            },
        }

    if row is not None:
        note = (
            f"Today's tax-deferred balances stand in for {prior}, because that "
            "snapshot has no owner and account breakdown. Snapshots recorded "
            "from now on include it, and next year's distribution can use "
            "this December 31."
        )
    else:
        note = (
            f"Today's tax-deferred balances stand in for {prior}, because no "
            "snapshot is stored for that date."
        )
    return {
        "source": "current",
        "as_of": as_of.isoformat(),
        "note": note,
        "balances": _current_rmd_balances(db),
    }

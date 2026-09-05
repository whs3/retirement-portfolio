"""Required Minimum Distribution (RMD) estimation.

Estimates only -- not tax advice. Uses the IRS Uniform Lifetime Table (the
table that applies to nearly everyone; it does not apply if a spouse is the
sole beneficiary and more than 10 years younger, which uses the lower Joint
and Last Survivor table instead). Treats the holding's *current* value as a
stand-in for the prior-year-end balance the IRS actually requires.
"""

from __future__ import annotations

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
    """Return this year's RMD estimate for one owner.

    ``balance`` should be the account's current value, used as a stand-in
    for the prior-year-end balance the IRS calculation actually requires.
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

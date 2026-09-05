"""Safe-withdrawal-rate projection.

A simple deterministic model (no Monte Carlo): the first year's withdrawal
is `rate% of the starting balance`; every year after that the withdrawal
grows with inflation rather than being recalculated as a % of the then
current balance, matching the classic "4% rule" / Trinity study methodology.
Each year, the withdrawal comes out first, then the remaining balance grows
at the assumed return for that year.
"""

from __future__ import annotations

from datetime import date

MAX_YEARS = 60


def project_withdrawals(
    starting_balance: float,
    annual_rate_pct: float,
    expected_return_pct: float,
    inflation_pct: float,
    years: int,
) -> dict:
    this_year = date.today().year
    withdrawal = starting_balance * annual_rate_pct / 100
    balance = starting_balance

    rows = []
    depletion_year = None
    for i in range(1, years + 1):
        start_balance = balance
        actual_withdrawal = min(withdrawal, balance) if balance > 0 else 0.0
        balance -= actual_withdrawal
        if balance <= 0:
            balance = 0.0
        else:
            balance *= 1 + expected_return_pct / 100

        rows.append({
            "year": i,
            "calendar_year": this_year + i,
            "start_balance": round(start_balance, 2),
            "withdrawal": round(actual_withdrawal, 2),
            "end_balance": round(balance, 2),
        })

        if start_balance > 0 and balance <= 0 and depletion_year is None:
            depletion_year = i

        withdrawal *= 1 + inflation_pct / 100

    return {
        "starting_balance": round(starting_balance, 2),
        "first_year_withdrawal": round(starting_balance * annual_rate_pct / 100, 2),
        "rows": rows,
        "depletion_year": depletion_year,
        "final_balance": rows[-1]["end_balance"] if rows else round(starting_balance, 2),
        "assumptions": {
            "annual_rate_pct": annual_rate_pct,
            "expected_return_pct": expected_return_pct,
            "inflation_pct": inflation_pct,
            "years": years,
        },
    }

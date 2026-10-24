"""Safe-withdrawal-rate projection.

A deterministic model. The planned withdrawal starts as ``rate%`` of today's
portfolio and then grows with inflation. Each year's gross withdrawal is at
least the household required distribution for that calendar year. The
withdrawal comes out first, then the remainder grows at the assumed return.

When account balances are supplied, the required distribution is taken from
pre-tax accounts and any amount above it is taken from taxable accounts, then
Roth, then more pre-tax. Pre-tax dollars are taxed at the ordinary rate,
taxable accounts at the gains rate, and Roth at zero. Spendable is the
withdrawal after that tax. The portfolio itself is reduced by the gross
withdrawal.
"""

from __future__ import annotations

from datetime import date

MAX_YEARS = 60

# Same pre-tax set the RMD estimate uses. Roth is tax-free. Everything else
# (Broker, Cash Management, and any account left blank) uses the gains rate.
PRETAX_ACCOUNT_TYPES = {"401k", "403b", "IRA", "Rollover IRA"}
ROTH_ACCOUNT_TYPES = {"Roth IRA"}


def tax_buckets_from_holdings(rows) -> dict[str, float]:
    """Split current holding values into pretax, taxable, and roth."""
    buckets = {"pretax": 0.0, "taxable": 0.0, "roth": 0.0}
    for row in rows:
        value = float(row["current_value"] or 0.0)
        account = row["account_type"] or ""
        if account in PRETAX_ACCOUNT_TYPES:
            buckets["pretax"] += value
        elif account in ROTH_ACCOUNT_TYPES:
            buckets["roth"] += value
        else:
            buckets["taxable"] += value
    return buckets


def _draw_buckets(buckets: dict, gross: float, rmd: float, ordinary_tax_pct: float, gains_tax_pct: float):
    """Take ``gross`` from the buckets. Returns updated buckets, tax, and sources."""
    pretax = buckets["pretax"]
    taxable = buckets["taxable"]
    roth = buckets["roth"]
    remaining = gross
    tax = 0.0
    sources = {"pretax": 0.0, "taxable": 0.0, "roth": 0.0}

    def take(pool: float, want: float, rate: float, key: str) -> float:
        nonlocal remaining, tax
        pulled = min(max(want, 0.0), max(pool, 0.0), max(remaining, 0.0))
        tax += pulled * rate / 100.0
        remaining -= pulled
        sources[key] += pulled
        return pool - pulled

    pretax = take(pretax, min(rmd, gross), ordinary_tax_pct, "pretax")
    taxable = take(taxable, remaining, gains_tax_pct, "taxable")
    roth = take(roth, remaining, 0.0, "roth")
    pretax = take(pretax, remaining, ordinary_tax_pct, "pretax")
    if remaining > 1e-9:
        # The portfolio total still has to fall by the withdrawal.
        pretax -= remaining
        tax += remaining * ordinary_tax_pct / 100.0
        sources["pretax"] += remaining
        remaining = 0.0
    return (
        {"pretax": pretax, "taxable": taxable, "roth": roth},
        tax,
        sources,
    )


def project_withdrawals(
    starting_balance: float,
    annual_rate_pct: float,
    expected_return_pct: float,
    inflation_pct: float,
    years: int,
    *,
    rmd_by_calendar_year: dict | None = None,
    buckets: dict | None = None,
    ordinary_tax_pct: float = 0.0,
    gains_tax_pct: float = 0.0,
    as_of: date | None = None,
) -> dict:
    anchor = as_of or date.today()
    planned = starting_balance * annual_rate_pct / 100
    rmd_schedule = rmd_by_calendar_year or {}
    balance = starting_balance
    state = None
    if buckets is not None:
        state = {
            "pretax": float(buckets.get("pretax") or 0.0),
            "taxable": float(buckets.get("taxable") or 0.0),
            "roth": float(buckets.get("roth") or 0.0),
        }
        balance = state["pretax"] + state["taxable"] + state["roth"]

    rows = []
    depletion_year = None
    growth = 1 + expected_return_pct / 100
    for i in range(1, years + 1):
        calendar_year = anchor.year + i
        rmd = max(0.0, float(rmd_schedule.get(calendar_year, 0.0) or 0.0))
        start_balance = balance
        gross_target = max(planned, rmd)
        actual = min(gross_target, start_balance) if start_balance > 0 else 0.0
        if state is None:
            balance -= actual
            if balance <= 0:
                balance = 0.0
            else:
                balance *= growth
            tax = 0.0
            sources = {"pretax": 0.0, "taxable": 0.0, "roth": 0.0}
        else:
            state, tax, sources = _draw_buckets(
                state, actual, rmd, ordinary_tax_pct, gains_tax_pct
            )
            for key, amount in state.items():
                state[key] = amount * growth
            balance = state["pretax"] + state["taxable"] + state["roth"]

        planned_capped = min(planned, start_balance) if start_balance > 0 else 0.0
        tax_rounded = round(tax, 2)
        actual_rounded = round(actual, 2)
        rows.append({
            "year": i,
            "calendar_year": calendar_year,
            "start_balance": round(start_balance, 2),
            "planned_withdrawal": round(planned_capped, 2),
            "rmd": round(rmd, 2),
            "withdrawal": actual_rounded,
            "tax": tax_rounded,
            "spendable": round(actual_rounded - tax_rounded, 2),
            "sources": {key: round(value, 2) for key, value in sources.items()},
            "end_balance": round(balance, 2),
        })

        if start_balance > 0 and balance <= 0 and depletion_year is None:
            depletion_year = i

        planned *= 1 + inflation_pct / 100

    starting_buckets = None
    if buckets is not None:
        starting_buckets = {
            "pretax": round(float(buckets.get("pretax") or 0.0), 2),
            "taxable": round(float(buckets.get("taxable") or 0.0), 2),
            "roth": round(float(buckets.get("roth") or 0.0), 2),
        }

    return {
        "starting_balance": round(starting_balance, 2),
        "first_year_withdrawal": round(starting_balance * annual_rate_pct / 100, 2),
        "rows": rows,
        "depletion_year": depletion_year,
        "final_balance": rows[-1]["end_balance"] if rows else round(starting_balance, 2),
        "tax_buckets": starting_buckets,
        "assumptions": {
            "annual_rate_pct": annual_rate_pct,
            "expected_return_pct": expected_return_pct,
            "inflation_pct": inflation_pct,
            "years": years,
            "ordinary_tax_pct": ordinary_tax_pct,
            "gains_tax_pct": gains_tax_pct,
        },
    }

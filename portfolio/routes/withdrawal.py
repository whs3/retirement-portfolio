"""Safe-withdrawal-rate projection API."""

from datetime import date, datetime

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.rmd import project_rmds, resolve_rmd_balances
from portfolio.services.settings import (
    get_owner_birthdates,
    get_tax_assumptions,
    get_withdrawal_assumptions,
    parse_withdrawal_rate,
    parse_withdrawal_years,
)
from portfolio.services.withdrawal import project_withdrawals, tax_buckets_from_holdings
from portfolio.timezone_util import today_iso

bp = Blueprint("withdrawal_api", __name__)


def _household_rmd_by_year(db, as_of: date, return_rate: float, years: int) -> dict[int, float]:
    """Combined Bill + Akiko RMD for each calendar year, using the same balances
    and return as ``/api/rmd``. ``years`` matches that projection's length, and
    one extra year is included so a plan that starts next calendar year still
    lines up with the last row.
    """
    resolved = resolve_rmd_balances(db, as_of)
    birthdates = get_owner_birthdates()
    combined: dict[int, float] = {}
    for owner in ("Bill", "Akiko"):
        raw = birthdates.get(owner)
        if not raw:
            continue
        birthdate = datetime.strptime(raw, "%Y-%m-%d").date()
        balance = resolved["balances"].get(owner, 0.0)
        for row in project_rmds(birthdate, balance, return_rate, years + 1, as_of=as_of):
            year = row["calendar_year"]
            combined[year] = round(combined.get(year, 0.0) + row["rmd_amount"], 2)
    return combined


@bp.route("/api/withdrawal")
def get_withdrawal_projection():
    defaults = get_withdrawal_assumptions()
    tax = get_tax_assumptions()
    args = request.args

    try:
        rate = (
            float(parse_withdrawal_rate(args["rate"], "Withdrawal rate"))
            if "rate" in args else defaults["withdrawal_rate"]
        )
        return_rate = (
            float(parse_withdrawal_rate(args["return_rate"], "Expected return"))
            if "return_rate" in args else defaults["withdrawal_return_rate"]
        )
        inflation_rate = (
            float(parse_withdrawal_rate(args["inflation_rate"], "Inflation rate"))
            if "inflation_rate" in args else defaults["withdrawal_inflation_rate"]
        )
        years = (
            int(parse_withdrawal_years(args["years"]))
            if "years" in args else defaults["withdrawal_years"]
        )
        ordinary_tax = (
            float(parse_withdrawal_rate(args["ordinary_tax"], "Ordinary tax rate"))
            if "ordinary_tax" in args else tax["tax_rate_ordinary"]
        )
        gains_tax = (
            float(parse_withdrawal_rate(args["gains_tax"], "Gains tax rate"))
            if "gains_tax" in args else tax["tax_rate_gains"]
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db = get_db()
    holdings = db.execute(
        "SELECT account_type, current_value FROM holdings"
    ).fetchall()
    total_value = sum(row["current_value"] or 0.0 for row in holdings)
    buckets = tax_buckets_from_holdings(holdings)
    as_of = date.fromisoformat(today_iso())
    rmd_by_year = _household_rmd_by_year(db, as_of, return_rate, years)

    result = project_withdrawals(
        total_value,
        rate,
        return_rate,
        inflation_rate,
        years,
        rmd_by_calendar_year=rmd_by_year,
        buckets=buckets,
        ordinary_tax_pct=ordinary_tax,
        gains_tax_pct=gains_tax,
        as_of=as_of,
    )
    return jsonify(result)

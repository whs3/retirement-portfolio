"""Required Minimum Distribution (RMD) estimate API."""

from datetime import date, datetime

from flask import Blueprint, jsonify

from portfolio.db import get_db
from portfolio.services.rmd import (
    RMD_SUBJECT_ACCOUNT_TYPES,
    calculate_rmd,
    project_rmds,
    resolve_rmd_balances,
)
from portfolio.services.settings import get_owner_birthdates, get_withdrawal_assumptions
from portfolio.timezone_util import today_iso

bp = Blueprint("rmd_api", __name__)


@bp.route("/api/rmd")
def get_rmd():
    db = get_db()
    as_of = date.fromisoformat(today_iso())
    resolved = resolve_rmd_balances(db, as_of)
    birthdates = get_owner_birthdates()
    assumptions = get_withdrawal_assumptions()
    return_rate = assumptions["withdrawal_return_rate"]
    projection_years = assumptions["withdrawal_years"]
    # The Uniform Lifetime factor uses the age attained on December 31.
    year_end = date(as_of.year, 12, 31)

    owners = []
    for owner in ("Bill", "Akiko"):
        balance = resolved["balances"].get(owner, 0.0)
        birthdate_str = birthdates.get(owner)
        entry = {
            "owner": owner,
            "balance": round(balance, 2),
            "birthdate": birthdate_str,
        }
        if birthdate_str:
            birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
            entry.update(calculate_rmd(birthdate, balance, as_of=year_end))
            entry["projection"] = project_rmds(
                birthdate, balance, return_rate, projection_years, as_of=as_of
            )
        owners.append(entry)

    return jsonify({
        "owners": owners,
        "account_types_included": sorted(RMD_SUBJECT_ACCOUNT_TYPES),
        "balance_source": resolved["source"],
        "balance_as_of": resolved["as_of"],
        "balance_note": resolved["note"],
        "projection_assumptions": {
            "return_rate_pct": return_rate,
            "years": projection_years,
        },
    })

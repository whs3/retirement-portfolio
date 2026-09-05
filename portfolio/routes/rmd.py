"""Required Minimum Distribution (RMD) estimate API."""

from datetime import date, datetime

from flask import Blueprint, jsonify

from portfolio.db import get_db
from portfolio.services.rmd import RMD_SUBJECT_ACCOUNT_TYPES, calculate_rmd
from portfolio.services.settings import get_owner_birthdates

bp = Blueprint("rmd_api", __name__)


@bp.route("/api/rmd")
def get_rmd():
    db = get_db()
    placeholders = ",".join("?" * len(RMD_SUBJECT_ACCOUNT_TYPES))
    rows = db.execute(
        f"""SELECT owner, SUM(current_value) AS balance
            FROM holdings
            WHERE owner IN ('Bill', 'Akiko') AND account_type IN ({placeholders})
            GROUP BY owner""",
        tuple(RMD_SUBJECT_ACCOUNT_TYPES),
    ).fetchall()
    balance_by_owner = {r["owner"]: r["balance"] or 0.0 for r in rows}
    birthdates = get_owner_birthdates()

    today = date.today()
    owners = []
    for owner in ("Bill", "Akiko"):
        balance = balance_by_owner.get(owner, 0.0)
        birthdate_str = birthdates.get(owner)
        entry = {
            "owner": owner,
            "balance": round(balance, 2),
            "birthdate": birthdate_str,
        }
        if birthdate_str:
            birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
            entry.update(calculate_rmd(birthdate, balance, as_of=today))
        owners.append(entry)

    return jsonify({
        "owners": owners,
        "account_types_included": sorted(RMD_SUBJECT_ACCOUNT_TYPES),
    })

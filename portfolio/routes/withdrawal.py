"""Safe-withdrawal-rate projection API."""

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.settings import (
    get_withdrawal_assumptions,
    parse_withdrawal_rate,
    parse_withdrawal_years,
)
from portfolio.services.withdrawal import project_withdrawals

bp = Blueprint("withdrawal_api", __name__)


@bp.route("/api/withdrawal")
def get_withdrawal_projection():
    defaults = get_withdrawal_assumptions()
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
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    total_value = get_db().execute(
        "SELECT COALESCE(SUM(current_value), 0) AS total FROM holdings"
    ).fetchone()["total"]

    result = project_withdrawals(total_value, rate, return_rate, inflation_rate, years)
    return jsonify(result)

"""Symbol lookup API."""

from flask import Blueprint, jsonify

from portfolio.services.lookup import lookup_ticker_data

bp = Blueprint("lookup_api", __name__)


@bp.route("/api/lookup/<ticker>")
def lookup_ticker(ticker):
    payload, status, error = lookup_ticker_data(ticker)
    if error:
        return jsonify({"error": error}), status
    return jsonify(payload)

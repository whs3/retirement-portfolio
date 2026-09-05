"""App settings API."""

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.audit import audit
from portfolio.services.settings import (
    ALLOWED_SETTINGS,
    BIRTHDATE_KEYS,
    PRICE_REFRESH_KEY,
    WITHDRAWAL_RATE_KEYS,
    WITHDRAWAL_YEARS_KEY,
    get_price_refresh_minutes,
    parse_birthdate,
    parse_price_refresh_minutes,
    parse_withdrawal_rate,
    parse_withdrawal_years,
)

bp = Blueprint("settings", __name__)


@bp.route("/api/settings", methods=["GET"])
def get_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    result = {r["key"]: r["value"] for r in rows}
    # Mask the API key in responses — return only whether it's set
    if "fmp_api_key" in result:
        result["fmp_api_key_set"] = bool(result["fmp_api_key"])
        del result["fmp_api_key"]
    result[PRICE_REFRESH_KEY] = str(get_price_refresh_minutes())
    return jsonify(result)


@bp.route("/api/settings", methods=["PUT"])
def update_settings():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400
    db = get_db()
    for key, value in data.items():
        if key not in ALLOWED_SETTINGS:
            return jsonify({"error": f"Unknown setting: {key}"}), 400
        if key == PRICE_REFRESH_KEY:
            try:
                minutes = parse_price_refresh_minutes(value)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            value = str(minutes)
        elif key in BIRTHDATE_KEYS:
            try:
                value = parse_birthdate(value)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        elif key in WITHDRAWAL_RATE_KEYS:
            try:
                value = parse_withdrawal_rate(value, key.replace("_", " "))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        elif key == WITHDRAWAL_YEARS_KEY:
            try:
                value = parse_withdrawal_years(value)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        elif not isinstance(value, str):
            return jsonify({"error": f"Invalid value for {key}"}), 400
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        audit("SETTING_UPDATE", "", "", key=key)
    db.commit()
    return jsonify({"success": True})

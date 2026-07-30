"""App settings API."""

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.audit import audit
from portfolio.services.settings import ALLOWED_SETTINGS

bp = Blueprint("settings", __name__)


@bp.route("/api/settings", methods=["GET"])
def get_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    result = {r["key"]: r["value"] for r in rows}
    # Mask the API key in responses — return only whether it's set
    if "fmp_api_key" in result:
        result["fmp_api_key_set"] = bool(result["fmp_api_key"])
        del result["fmp_api_key"]
    return jsonify(result)


@bp.route("/api/settings", methods=["PUT"])
def update_settings():
    data = request.get_json()
    db = get_db()
    for key, value in data.items():
        if key not in ALLOWED_SETTINGS:
            return jsonify({"error": f"Unknown setting: {key}"}), 400
        if not isinstance(value, str):
            return jsonify({"error": f"Invalid value for {key}"}), 400
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        audit("SETTING_UPDATE", "", "", key=key)
    db.commit()
    return jsonify({"success": True})

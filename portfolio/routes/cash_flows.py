"""Manual cash-flow API. Automatic flows are written from holdings changes."""

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.audit import audit
from portfolio.services.cash_flows import (
    delete_cash_flow,
    get_cash_flow,
    insert_cash_flow,
    parse_manual_flow,
)

bp = Blueprint("cash_flows_api", __name__)


@bp.route("/api/cash-flows", methods=["POST"])
def add_cash_flow():
    data = request.get_json(silent=True)
    try:
        fields = parse_manual_flow(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db = get_db()
    flow_id = insert_cash_flow(db, **fields)
    db.commit()
    if flow_id is None:
        return jsonify({"error": "Amount cannot be zero"}), 400

    audit(
        "CASHFLOW",
        fields["ticker"],
        fields["note"] or "Cash flow",
        amount=fields["amount"],
    )
    row = get_cash_flow(db, flow_id)
    return jsonify(row), 201


@bp.route("/api/cash-flows/<int:flow_id>", methods=["DELETE"])
def remove_cash_flow(flow_id):
    deleted = delete_cash_flow(get_db(), flow_id)
    if deleted is None:
        return jsonify({"error": "Not found"}), 404
    audit(
        "CASHFLOW_DELETE",
        deleted["ticker"],
        deleted["note"] or "Cash flow",
        amount=deleted["amount"],
    )
    return jsonify({"success": True})

"""Holdings CRUD and sell-all API."""

from datetime import datetime

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.services.audit import audit
from portfolio.validators import VALID_TICKER, is_significant_value, parse_float

bp = Blueprint("holdings", __name__)


@bp.route("/api/holdings", methods=["GET"])
def get_holdings():
    rows = get_db().execute(
        "SELECT * FROM holdings ORDER BY asset_type, name"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/holdings", methods=["POST"])
def add_holding():
    data = request.get_json()
    missing = [
        f for f in ("name", "asset_type", "cost_basis", "current_value")
        if not data.get(f) and data.get(f) != 0
    ]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        shares = parse_float(data.get("shares") or 0, "Shares")
        cost_basis = parse_float(data["cost_basis"], "Cost Basis")
        current_val = parse_float(data["current_value"], "Current Value")
    except (ValueError, KeyError) as exc:
        return jsonify({"error": str(exc)}), 400

    if (data.get("ticker") or "").strip().upper() == "$$CASH":
        data["category"] = "Cash"
        current_val = shares

    now = datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            (data.get("ticker") or "").strip().upper(),
            data["asset_type"],
            (data.get("category") or "").strip(),
            (data.get("owner") or "").strip(),
            (data.get("account_type") or "").strip(),
            shares,
            cost_basis,
            current_val,
            data.get("purchase_date") or "",
            (data.get("notes") or "").strip(),
            now,
            now,
        ),
    )
    db.commit()
    audit(
        "ADD",
        (data.get("ticker") or "").strip().upper(),
        data["name"].strip(),
        current_value=current_val,
        cost_basis=cost_basis,
    )
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@bp.route("/api/holdings/<int:hid>", methods=["PUT"])
def update_holding(hid):
    data = request.get_json()
    db = get_db()
    row = db.execute("SELECT * FROM holdings WHERE id = ?", (hid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    ticker = (data.get("ticker") or row["ticker"]).strip().upper()

    try:
        new_shares = parse_float(
            data["shares"] if data.get("shares") is not None else row["shares"], "Shares"
        )
        new_cost = parse_float(
            data["cost_basis"] if data.get("cost_basis") is not None else row["cost_basis"],
            "Cost Basis",
        )
        new_value = parse_float(
            data["current_value"]
            if data.get("current_value") is not None
            else row["current_value"],
            "Current Value",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if ticker == "$$CASH":
        data["category"] = "Cash"
        new_value = new_shares

    now = datetime.utcnow().isoformat()
    db.execute(
        """UPDATE holdings
           SET name=?, ticker=?, asset_type=?, category=?, owner=?, account_type=?,
               shares=?, cost_basis=?, current_value=?, purchase_date=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            (data.get("name") or row["name"]).strip(),
            ticker,
            data.get("asset_type") or row["asset_type"],
            (
                data.get("category")
                if data.get("category") is not None
                else row["category"]
            ).strip(),
            (
                data.get("owner")
                if data.get("owner") is not None
                else (row["owner"] or "")
            ).strip(),
            (
                data.get("account_type")
                if data.get("account_type") is not None
                else (row["account_type"] or "")
            ).strip(),
            new_shares,
            new_cost,
            new_value,
            data.get("purchase_date") or row["purchase_date"],
            (data.get("notes") or row["notes"]).strip(),
            now,
            hid,
        ),
    )
    db.commit()
    audit(
        "EDIT",
        (data.get("ticker") or row["ticker"]).strip().upper(),
        (data.get("name") or row["name"]).strip(),
        value_change=new_value - row["current_value"],
        cost_basis_change=new_cost - row["cost_basis"],
        current_value=new_value,
        cost_basis=new_cost,
    )
    return jsonify({"success": True})


@bp.route("/api/holdings/<int:hid>", methods=["DELETE"])
def delete_holding(hid):
    db = get_db()
    row = db.execute("SELECT * FROM holdings WHERE id = ?", (hid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM holdings WHERE id = ?", (hid,))
    db.commit()
    audit(
        "DELETE",
        row["ticker"],
        row["name"],
        current_value=row["current_value"],
        cost_basis=row["cost_basis"],
    )
    return jsonify({"success": True})


@bp.route("/api/holdings/sell-all", methods=["POST"])
def sell_all_holding():
    """Close out a position by collapsing every matching lot into a single
    zeroed-out row for the given ticker+owner+account_type.

    Individual lots each get their own current_value re-rounded to the cent
    on every price refresh (see services.prices.refresh_all_prices), so
    appending one offsetting lot next to the originals cannot reliably keep
    the group's total at exactly $0 -- the untouched original lots keep
    re-rounding independently every refresh cycle and drift a cent or two
    away from zero. Deleting the lots and replacing them with one row at
    shares=0 sidesteps that: 0 shares always reprices to exactly $0.00, no
    matter how many refreshes happen afterward.
    """
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").strip().upper()
    owner = (data.get("owner") or "").strip()
    account_type = (data.get("account_type") or "").strip()

    if not ticker:
        return jsonify({"error": "Ticker is required"}), 400
    if not VALID_TICKER.match(ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    db = get_db()
    rows = db.execute(
        "SELECT * FROM holdings WHERE ticker=? AND owner=? AND account_type=?",
        (ticker, owner, account_type),
    ).fetchall()
    if not rows:
        return jsonify({"error": "No matching holding found"}), 404

    total_shares = sum(r["shares"] for r in rows)
    total_cost_basis = sum(r["cost_basis"] for r in rows)
    total_current_value = sum(r["current_value"] for r in rows)

    already_flat = len(rows) == 1 and rows[0]["shares"] == 0 and rows[0]["cost_basis"] == 0
    if already_flat or (
        abs(total_shares) < 1e-6 and not is_significant_value(total_current_value)
    ):
        return jsonify({"error": f"{ticker} is already fully sold"}), 400

    ref = rows[0]
    now = datetime.utcnow().isoformat()
    db.executemany(
        "DELETE FROM holdings WHERE id = ?", [(r["id"],) for r in rows]
    )
    cur = db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?)""",
        (
            ref["name"],
            ticker,
            ref["asset_type"],
            ref["category"],
            owner,
            account_type,
            datetime.utcnow().strftime("%Y-%m-%d"),
            "Sold all shares",
            now,
            now,
        ),
    )
    db.commit()
    audit(
        "SELL_ALL",
        ticker,
        ref["name"],
        shares=-total_shares,
        current_value=-total_current_value,
        cost_basis=-total_cost_basis,
    )
    return jsonify({
        "id": cur.lastrowid,
        "success": True,
        "shares_sold": total_shares,
        "value_sold": total_current_value,
    }), 201

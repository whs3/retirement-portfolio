"""Portfolio summary, target allocations, and rebalance API."""

from flask import Blueprint, jsonify, request

from portfolio.db import get_db
from portfolio.validators import NEGLIGIBLE_VALUE

bp = Blueprint("portfolio_api", __name__)


@bp.route("/api/portfolio/summary")
def portfolio_summary():
    holdings = get_db().execute("SELECT * FROM holdings").fetchall()
    total_value = sum(h["current_value"] for h in holdings)
    total_cost = sum(h["cost_basis"] for h in holdings)
    gain_loss = total_value - total_cost
    gain_loss_pct = (gain_loss / total_cost * 100) if total_cost else 0

    by_type: dict[str, float] = {}
    for h in holdings:
        by_type.setdefault(h["asset_type"], 0)
        by_type[h["asset_type"]] += h["current_value"]

    allocation = [
        {
            "asset_type": t,
            "value": v,
            "percentage": (v / total_value * 100) if total_value else 0,
        }
        for t, v in sorted(by_type.items())
        if abs(v) > NEGLIGIBLE_VALUE
    ]

    by_category: dict[str, float] = {}
    by_category_tickers: dict[str, set] = {}
    for h in holdings:
        cat = h["category"] or "Uncategorized"
        by_category.setdefault(cat, 0)
        by_category[cat] += h["current_value"]
        by_category_tickers.setdefault(cat, set())
        key = h["ticker"] if h["ticker"] else f"__no_ticker_{h['id']}"
        by_category_tickers[cat].add(key)

    category_allocation = [
        {
            "category": cat,
            "value": val,
            "percentage": (val / total_value * 100) if total_value else 0,
            "positions": len(by_category_tickers.get(cat, set())),
        }
        for cat, val in sorted(by_category.items())
        if abs(val) > NEGLIGIBLE_VALUE
    ]

    by_owner: dict[str, float] = {}
    by_account_type: dict[str, float] = {}
    for h in holdings:
        owner = (h["owner"] or "Unassigned") if "owner" in h.keys() else "Unassigned"
        acct = (h["account_type"] or "Unassigned") if "account_type" in h.keys() else "Unassigned"
        by_owner.setdefault(owner, 0)
        by_owner[owner] += h["current_value"]
        by_account_type.setdefault(acct, 0)
        by_account_type[acct] += h["current_value"]

    owner_allocation = [
        {"owner": o, "value": v, "percentage": (v / total_value * 100) if total_value else 0}
        for o, v in sorted(by_owner.items())
        if abs(v) > NEGLIGIBLE_VALUE
    ]
    account_type_allocation = [
        {
            "account_type": a,
            "value": v,
            "percentage": (v / total_value * 100) if total_value else 0,
        }
        for a, v in sorted(by_account_type.items())
        if abs(v) > NEGLIGIBLE_VALUE
    ]

    return jsonify({
        "total_value": total_value,
        "total_cost": total_cost,
        "gain_loss": gain_loss,
        "gain_loss_pct": gain_loss_pct,
        "count": len(holdings),
        "allocation": allocation,
        "category_allocation": category_allocation,
        "owner_allocation": owner_allocation,
        "account_type_allocation": account_type_allocation,
    })


@bp.route("/api/allocations", methods=["GET"])
def get_allocations():
    db = get_db()
    holding_cats = db.execute(
        "SELECT DISTINCT COALESCE(NULLIF(category,''), 'Uncategorized') AS cat FROM holdings"
    ).fetchall()
    targets = db.execute("SELECT * FROM target_allocations").fetchall()
    target_map = {t["category"]: t["target_percentage"] for t in targets}
    all_cats = set(r["cat"] for r in holding_cats) | set(target_map)
    result = sorted(
        [{"category": c, "target_percentage": target_map.get(c, 0)} for c in all_cats],
        key=lambda x: x["category"],
    )
    return jsonify(result)


@bp.route("/api/allocations", methods=["PUT"])
def update_allocations():
    data = request.get_json()  # [{category, target_percentage}, ...]
    total = sum(float(item["target_percentage"]) for item in data)
    if abs(total - 100) > 0.01:
        return jsonify({
            "error": f"Allocations must sum to 100% (currently {total:.1f}%)"
        }), 400

    db = get_db()
    for item in data:
        db.execute(
            """INSERT INTO target_allocations (category, target_percentage)
               VALUES (?, ?)
               ON CONFLICT(category) DO UPDATE SET target_percentage = excluded.target_percentage""",
            (item["category"], float(item["target_percentage"])),
        )
    db.commit()
    return jsonify({"success": True})


@bp.route("/api/rebalance")
def get_rebalance():
    db = get_db()
    holdings = db.execute("SELECT * FROM holdings").fetchall()
    targets = db.execute("SELECT * FROM target_allocations").fetchall()

    total_value = sum(h["current_value"] for h in holdings)

    current: dict[str, float] = {}
    for h in holdings:
        cat = h["category"] or "Uncategorized"
        current.setdefault(cat, 0)
        current[cat] += h["current_value"]

    target_map = {t["category"]: t["target_percentage"] for t in targets}
    all_cats = set(current) | set(target_map)

    recommendations = []
    for cat in all_cats:
        target_pct = target_map.get(cat, 0)
        curr_val = current.get(cat, 0)
        curr_pct = (curr_val / total_value * 100) if total_value else 0
        target_val = total_value * target_pct / 100
        diff = target_val - curr_val
        recommendations.append({
            "category": cat,
            "current_value": curr_val,
            "current_pct": curr_pct,
            "target_pct": target_pct,
            "target_value": target_val,
            "difference": diff,
            "action": "Buy" if diff > 1 else "Sell" if diff < -1 else "Hold",
        })

    return jsonify({
        "total_value": total_value,
        "recommendations": sorted(recommendations, key=lambda x: x["category"]),
    })

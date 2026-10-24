"""Category rebalance recommendations, with an account and ticker for each trade.

Sells are filled from taxable accounts (Broker, Cash Management) before Roth,
and from Roth before pre-tax IRAs and workplace plans. Buys name the accounts
that already hold the category.
"""

from __future__ import annotations

from portfolio.validators import is_significant_value

# Lower rank is sold first. Taxable accounts share a rank so the larger lot
# is used first. Unknown account types come last.
_ACCOUNT_RANK = {
    "Broker": 0,
    "Cash Management": 0,
    "Roth IRA": 1,
    "IRA": 2,
    "Rollover IRA": 2,
    "401k": 3,
    "403b": 3,
}


def _rank(account_type: str) -> int:
    return _ACCOUNT_RANK.get(account_type or "", 9)


def _positions_for(holdings, category: str) -> list[dict]:
    rows = []
    for holding in holdings:
        cat = holding["category"] or "Uncategorized"
        if cat != category:
            continue
        value = float(holding["current_value"] or 0.0)
        if not is_significant_value(value):
            continue
        ticker = (holding["ticker"] or "").strip().upper()
        rows.append({
            "ticker": ticker,
            "name": holding["name"] or ticker,
            "owner": holding["owner"] or "",
            "account_type": holding["account_type"] or "",
            "current_value": round(value, 2),
        })
    rows.sort(key=lambda row: (
        _rank(row["account_type"]),
        -row["current_value"],
        row["owner"],
        row["ticker"],
        row["name"],
    ))
    return rows


def _sell_trades(positions: list[dict], amount: float) -> list[dict]:
    remaining = round(max(amount, 0.0), 2)
    trades = []
    for position in positions:
        if remaining < 0.01:
            break
        if position["current_value"] <= 0:
            continue
        take = round(min(position["current_value"], remaining), 2)
        if take < 0.01:
            continue
        trades.append({
            "side": "Sell",
            "ticker": position["ticker"],
            "name": position["name"],
            "owner": position["owner"],
            "account_type": position["account_type"],
            "amount": take,
        })
        remaining = round(remaining - take, 2)
    return trades


def build_recommendations(holdings, targets, drift_threshold_pts: float) -> dict:
    """One row per category. ``difference`` is target dollars minus current dollars."""
    total_value = sum(float(h["current_value"] or 0.0) for h in holdings)

    current: dict[str, float] = {}
    for holding in holdings:
        cat = holding["category"] or "Uncategorized"
        current[cat] = current.get(cat, 0.0) + float(holding["current_value"] or 0.0)

    target_map = {t["category"]: t["target_percentage"] for t in targets}
    recommendations = []
    for cat in set(current) | set(target_map):
        target_pct = target_map.get(cat, 0)
        curr_val = current.get(cat, 0.0)
        curr_pct = (curr_val / total_value * 100) if total_value else 0.0
        target_val = total_value * target_pct / 100
        diff = target_val - curr_val
        drift = abs(curr_pct - target_pct)
        if abs(diff) < 0.01 or drift < drift_threshold_pts:
            action = "Hold"
        elif diff > 0:
            action = "Buy"
        else:
            action = "Sell"

        positions = _positions_for(holdings, cat)
        if action == "Sell":
            trades = _sell_trades(positions, -diff)
            note = "Taxable accounts are sold before IRAs."
        elif action == "Buy" and positions:
            trades = []
            note = "Add to an account that already holds this category."
        elif action == "Buy":
            trades = []
            note = "No holding in this category yet."
        else:
            trades = []
            note = ""

        recommendations.append({
            "category": cat,
            "current_value": curr_val,
            "current_pct": curr_pct,
            "target_pct": target_pct,
            "target_value": target_val,
            "difference": diff,
            "action": action,
            "positions": positions,
            "trades": trades,
            "note": note,
        })

    return {
        "total_value": total_value,
        "drift_threshold_pts": drift_threshold_pts,
        "recommendations": sorted(recommendations, key=lambda row: row["category"]),
    }

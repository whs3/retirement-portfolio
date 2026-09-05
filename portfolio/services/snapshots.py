"""Daily portfolio value snapshots.

Rather than recomputing 12 months of history from live yfinance calls on every
``/api/performance`` request, this module maintains one row per calendar date
in ``portfolio_snapshots`` with the actual portfolio value on that date. Once
captured, a day's value never depends on yfinance being reachable again.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

from portfolio.db import get_db
from portfolio.services.performance import build_performance
from portfolio.validators import NEGLIGIBLE_VALUE, is_significant_value


def capture_snapshot() -> None:
    """Upsert today's row from the current holdings table (no network calls)."""
    db = get_db()
    holdings_rows = db.execute("SELECT * FROM holdings").fetchall()

    total_value = sum(h["current_value"] for h in holdings_rows)
    total_cost_basis = sum(h["cost_basis"] for h in holdings_rows)

    # Same cash-ticker rule as services.performance.build_performance: a ticker
    # with any cash-type row is treated as constant value everywhere.
    cash_tickers: set[str] = set()
    for h in holdings_rows:
        t = (h["ticker"] or "").strip().upper()
        if t and t != "$$CASH" and h["asset_type"] == "cash":
            cash_tickers.add(t)

    value_by_ticker: dict[str, float] = {}
    name_by_ticker: dict[str, str] = {}
    asset_type_by_ticker: dict[str, str] = {}
    category_by_ticker: dict[str, str] = {}
    untracked_value = 0.0

    for h in holdings_rows:
        ticker = (h["ticker"] or "").strip().upper()
        if not ticker or ticker == "$$CASH" or h["asset_type"] == "cash" or ticker in cash_tickers:
            untracked_value += h["current_value"]
            continue
        value_by_ticker[ticker] = value_by_ticker.get(ticker, 0.0) + h["current_value"]
        name_by_ticker.setdefault(ticker, h["name"] or ticker)
        asset_type_by_ticker.setdefault(ticker, h["asset_type"] or "")
        if h["category"]:
            category_by_ticker[ticker] = h["category"]

    holdings_json: dict[str, dict] = {}
    category_json: dict[str, float] = {}
    for ticker, value in value_by_ticker.items():
        if not is_significant_value(value):
            continue
        category = category_by_ticker.get(ticker) or "Uncategorized"
        holdings_json[ticker] = {
            "name": name_by_ticker.get(ticker, ticker),
            "value": round(value, 2),
            "asset_type": asset_type_by_ticker.get(ticker, ""),
            "category": category,
        }
        category_json[category] = category_json.get(category, 0.0) + round(value, 2)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    now_iso = datetime.utcnow().isoformat()
    db.execute(
        """INSERT INTO portfolio_snapshots
               (date, total_value, total_cost_basis, category_json, holdings_json,
                untracked_value, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               total_value=excluded.total_value,
               total_cost_basis=excluded.total_cost_basis,
               category_json=excluded.category_json,
               holdings_json=excluded.holdings_json,
               untracked_value=excluded.untracked_value""",
        (
            today,
            round(total_value, 2),
            round(total_cost_basis, 2),
            json.dumps(category_json),
            json.dumps(holdings_json),
            round(untracked_value, 2),
            now_iso,
        ),
    )
    db.commit()


_BACKFILL_MARKER_KEY = "performance_backfilled_at"


def backfill_once() -> None:
    """Seed ~365 days of approximate history the first time this ever runs.

    Reuses build_performance()'s existing (current-shares x historical-price)
    approximation as a one-time bootstrap so Performance isn't blank on first
    use; every day after this, capture_snapshot() records the real value.

    Gated on a settings-table marker rather than an empty portfolio_snapshots
    table: the auto-refresh scheduler calls capture_snapshot() independently
    of this function and can write today's row first, which would make an
    empty-table check a permanent false negative and leave Performance stuck
    on a single day of history.
    """
    db = get_db()
    already_done = db.execute(
        "SELECT 1 FROM settings WHERE key = ?", (_BACKFILL_MARKER_KEY,)
    ).fetchone()
    if already_done:
        return

    result = build_performance()
    dates = result.get("dates") or []
    values = result.get("values") or []
    holdings_series = result.get("holdings_series") or []
    categories_series = result.get("categories_series") or []
    untracked_value = result.get("untracked_value") or 0.0
    total_cost_basis = db.execute(
        "SELECT COALESCE(SUM(cost_basis), 0) AS c FROM holdings"
    ).fetchone()["c"]

    now_iso = datetime.utcnow().isoformat()
    for i, date in enumerate(dates):
        holdings_json = {
            h["ticker"]: {
                "name": h["name"],
                "value": h["values"][i],
                "asset_type": "",
                "category": h.get("category") or "Uncategorized",
            }
            for h in holdings_series
            if i < len(h["values"])
        }
        category_json = {
            c["category"]: c["values"][i]
            for c in categories_series
            if i < len(c["values"])
        }
        db.execute(
            """INSERT INTO portfolio_snapshots
                   (date, total_value, total_cost_basis, category_json, holdings_json,
                    untracked_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO NOTHING""",
            (
                date,
                round(values[i], 2),
                round(total_cost_basis, 2),
                json.dumps(category_json),
                json.dumps(holdings_json),
                round(untracked_value, 2),
                now_iso,
            ),
        )
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_BACKFILL_MARKER_KEY, now_iso),
    )
    db.commit()
    # Overwrite today's backfilled estimate (if any) with a real, live-computed value.
    capture_snapshot()


def get_performance_history(days: int = 365) -> dict:
    """Read stored snapshots and reshape them into build_performance()'s response
    shape, so static/js/performance.js needs no changes."""
    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT * FROM portfolio_snapshots WHERE date >= ? ORDER BY date ASC",
        (cutoff,),
    ).fetchall()

    if not rows:
        return {
            "dates": [],
            "values": [],
            "summary": {},
            "monthly": [],
            "holdings_series": [],
            "categories_series": [],
            "untracked": [],
            "untracked_value": 0.0,
        }

    dates = [r["date"] for r in rows]
    values = [round(r["total_value"], 2) for r in rows]

    per_row_holdings = [json.loads(r["holdings_json"] or "{}") for r in rows]
    all_tickers: set[str] = set()
    for hj in per_row_holdings:
        all_tickers.update(hj.keys())

    holdings_series = []
    for ticker in all_tickers:
        series: list[float] = []
        last_value = 0.0
        name = ticker
        category = "Uncategorized"
        for hj in per_row_holdings:
            info = hj.get(ticker)
            if info is not None:
                last_value = info["value"]
                name = info.get("name", name)
                category = info.get("category") or category
            series.append(round(last_value, 2))
        if not series or max(abs(v) for v in series) <= NEGLIGIBLE_VALUE:
            continue
        holdings_series.append({
            "ticker": ticker,
            "name": name,
            "category": category,
            "values": series,
        })
    holdings_series.sort(key=lambda x: x["values"][-1] if x["values"] else 0, reverse=True)

    cat_totals: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(dates))
    for h in holdings_series:
        for i, v in enumerate(h["values"]):
            cat_totals[h["category"]][i] += v
    categories_series = sorted(
        [
            {"category": cat, "values": [round(v, 2) for v in vals]}
            for cat, vals in cat_totals.items()
        ],
        key=lambda x: x["values"][-1] if x["values"] else 0,
        reverse=True,
    )

    start_val = values[0]
    end_val = values[-1]
    gain = end_val - start_val
    gain_pct = (gain / start_val * 100) if start_val else 0
    peak_val = max(values)
    trough_val = min(values)

    series = pd.Series(values, index=pd.to_datetime(dates))
    monthly_first = series.resample("MS").first()
    monthly_last = series.resample("MS").last()
    monthly = []
    for month in monthly_last.index:
        m_start = float(monthly_first.get(month, monthly_last[month]))
        m_end = float(monthly_last[month])
        m_gain = m_end - m_start
        m_pct = (m_gain / m_start * 100) if m_start else 0
        monthly.append({
            "month": month.strftime("%b %Y"),
            "start": round(m_start, 2),
            "end": round(m_end, 2),
            "gain": round(m_gain, 2),
            "gain_pct": round(m_pct, 2),
        })

    return {
        "dates": dates,
        "values": values,
        "summary": {
            "start_value": round(start_val, 2),
            "end_value": round(end_val, 2),
            "gain": round(gain, 2),
            "gain_pct": round(gain_pct, 2),
            "peak_value": round(peak_val, 2),
            "trough_value": round(trough_val, 2),
        },
        "monthly": monthly,
        "holdings_series": holdings_series,
        "categories_series": categories_series,
        "untracked": [],
        "untracked_value": round(rows[-1]["untracked_value"], 2),
    }

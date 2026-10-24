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
import yfinance as yf

from portfolio.db import get_db
from portfolio.services.cash_flows import list_cash_flows, period_return
from portfolio.services.performance import build_performance
from portfolio.timezone_util import now_iso, now_local, today_iso
from portfolio.validators import NEGLIGIBLE_VALUE, is_significant_value

_SHARE_EPS = 1e-6


def owner_accounts_from_holdings(holdings_rows) -> dict:
    """Owner → account type → value, including cash.

    Rounded buckets under one cent are dropped. An empty dict means the
    breakdown was captured and nothing was held, which is different from a
    missing snapshot column.
    """
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for h in holdings_rows:
        owner = (h["owner"] or "").strip() or "Unassigned"
        account = (h["account_type"] or "").strip() or "Unassigned"
        totals[owner][account] += h["current_value"] or 0.0
    result: dict[str, dict[str, float]] = {}
    for owner, accounts in totals.items():
        rounded = {
            account: round(value, 2)
            for account, value in accounts.items()
            if abs(round(value, 2)) >= 0.01
        }
        if rounded:
            result[owner] = rounded
    return result


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
    shares_by_ticker: dict[str, float] = {}
    # A lot with value but no share count makes value / shares meaningless.
    unknown_shares: set[str] = set()
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
        shares_by_ticker[ticker] = shares_by_ticker.get(ticker, 0.0) + (h["shares"] or 0.0)
        if not h["shares"] and is_significant_value(h["current_value"] or 0.0):
            unknown_shares.add(ticker)
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
        shares = shares_by_ticker.get(ticker, 0.0)
        if ticker not in unknown_shares and abs(shares) > _SHARE_EPS:
            holdings_json[ticker]["shares"] = round(shares, 6)
            holdings_json[ticker]["price"] = round(value / shares, 4)
        category_json[category] = category_json.get(category, 0.0) + round(value, 2)

    today = today_iso()
    captured_at = now_iso()
    owner_accounts_json = json.dumps(owner_accounts_from_holdings(holdings_rows))
    db.execute(
        """INSERT INTO portfolio_snapshots
               (date, total_value, total_cost_basis, category_json, holdings_json,
                untracked_value, created_at, owner_accounts_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               total_value=excluded.total_value,
               total_cost_basis=excluded.total_cost_basis,
               category_json=excluded.category_json,
               holdings_json=excluded.holdings_json,
               untracked_value=excluded.untracked_value,
               owner_accounts_json=excluded.owner_accounts_json""",
        (
            today,
            round(total_value, 2),
            round(total_cost_basis, 2),
            json.dumps(category_json),
            json.dumps(holdings_json),
            round(untracked_value, 2),
            captured_at,
            owner_accounts_json,
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

    captured_at = now_iso()
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
                captured_at,
            ),
        )
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_BACKFILL_MARKER_KEY, captured_at),
    )
    db.commit()
    # Overwrite today's backfilled estimate (if any) with a real, live-computed value.
    capture_snapshot()


_PRICE_BACKFILL_MARKER_KEY = "snapshot_prices_backfilled_at"


def _fetch_closes(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Unadjusted daily closes (index=date, columns=tickers) from yfinance.

    Unadjusted so they line up with the live regularMarketPrice that
    capture_snapshot() records from then on.
    """
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        multi_level_index=True,
    )
    if raw.empty:
        return pd.DataFrame()
    return raw["Close"]


def backfill_prices_once() -> None:
    """Add a per-ticker ``price`` to snapshots captured before prices were stored.

    The Individual Holdings chart plots price change so that buying or selling
    shares is not drawn as performance. Rows from before that change only have
    values, so their price comes from that day's close (or the last close
    before a weekend or holiday). Runs once, gated on a settings marker; if
    yfinance returns nothing the marker is not set and the next request retries.
    Tickers yfinance has no history for keep no price, and the chart falls
    back to value for them.
    """
    db = get_db()
    if db.execute(
        "SELECT 1 FROM settings WHERE key = ?", (_PRICE_BACKFILL_MARKER_KEY,)
    ).fetchone():
        return

    rows = db.execute(
        "SELECT date, holdings_json FROM portfolio_snapshots ORDER BY date"
    ).fetchall()
    pending: list[tuple[str, dict]] = []
    tickers: set[str] = set()
    for r in rows:
        hj = json.loads(r["holdings_json"] or "{}")
        missing = [t for t, info in hj.items() if "price" not in info]
        if missing:
            pending.append((r["date"], hj))
            tickers.update(missing)

    if pending:
        start = (
            datetime.strptime(pending[0][0], "%Y-%m-%d") - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        end = (
            datetime.strptime(pending[-1][0], "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        try:
            close = _fetch_closes(sorted(tickers), start, end)
        except Exception:
            return
        if close.empty:
            return
        close = close.ffill()
        close.index = pd.to_datetime(close.index).strftime("%Y-%m-%d")

        for date, hj in pending:
            on_or_before = close[close.index <= date]
            if on_or_before.empty:
                continue
            day = on_or_before.iloc[-1]
            changed = False
            for ticker, info in hj.items():
                if "price" in info or ticker not in day.index:
                    continue
                price = day[ticker]
                if pd.isna(price) or price <= 0:
                    continue
                info["price"] = round(float(price), 4)
                changed = True
            if changed:
                db.execute(
                    "UPDATE portfolio_snapshots SET holdings_json = ? WHERE date = ?",
                    (json.dumps(hj), date),
                )

    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_PRICE_BACKFILL_MARKER_KEY, now_iso()),
    )
    db.commit()


def get_performance_history(days: int = 365) -> dict:
    """Read stored snapshots and reshape them for the Performance page.

    ``summary.gain`` is the investment gain: the change in portfolio value
    minus cash flows between the first and last snapshot. Per-holding values
    are zero on days the ticker is absent, so a sale does not stay on the chart.
    """
    db = get_db()
    cutoff = (now_local().date() - timedelta(days=days)).isoformat()
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
            "cash_flows": [],
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
        prices: list[float | None] = []
        name = ticker
        category = "Uncategorized"
        for hj in per_row_holdings:
            info = hj.get(ticker)
            if info is not None:
                name = info.get("name", name)
                category = info.get("category") or category
                series.append(round(info["value"], 2))
                prices.append(info.get("price"))
            else:
                # Absent means sold or not yet held. Carrying the previous
                # value forward kept closed positions on the chart forever.
                series.append(0.0)
                prices.append(None)
        if not series or max(abs(v) for v in series) <= NEGLIGIBLE_VALUE:
            continue
        holdings_series.append({
            "ticker": ticker,
            "name": name,
            "category": category,
            "values": series,
            # Per-share price on days held, else None. The holdings chart uses
            # it so trades are not drawn as gains or losses.
            "prices": prices,
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
    # The whole ledger, not just this window. Period math ignores flows outside
    # the snapshots, and the page can still show an older entry the user added.
    cash_flows = list_cash_flows(db)
    stats = period_return(dates, values, cash_flows)
    peak_val = max(values)
    trough_val = min(values)

    by_month: dict[str, list[int]] = defaultdict(list)
    for i, day in enumerate(dates):
        by_month[day[:7]].append(i)
    monthly = []
    for ym in sorted(by_month):
        idxs = by_month[ym]
        i0, i1 = idxs[0], idxs[-1]
        month_dates = [dates[i] for i in idxs]
        month_values = [values[i] for i in idxs]
        month_stats = period_return(month_dates, month_values, cash_flows)
        monthly.append({
            "month": datetime.strptime(ym, "%Y-%m").strftime("%b %Y"),
            "start": round(values[i0], 2),
            "end": round(values[i1], 2),
            **month_stats,
        })

    return {
        "dates": dates,
        "values": values,
        "summary": {
            "start_value": round(start_val, 2),
            "end_value": round(end_val, 2),
            "peak_value": round(peak_val, 2),
            "trough_value": round(trough_val, 2),
            **stats,
        },
        "monthly": monthly,
        "cash_flows": cash_flows,
        "holdings_series": holdings_series,
        "categories_series": categories_series,
        "untracked": [],
        "untracked_value": round(rows[-1]["untracked_value"], 2),
    }

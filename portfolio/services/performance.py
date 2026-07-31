"""Portfolio performance history from current shares × historical prices."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from portfolio.db import get_db
from portfolio.services.categories import ASSET_TYPE_FALLBACK, get_ticker_category
from portfolio.validators import NEGLIGIBLE_VALUE


def build_performance() -> dict:
    """
    Return daily portfolio values for the past 12 months calculated as
    current shares × historical closing prices.

    Holdings without a ticker (or whose history can't be fetched) are included
    as a constant contribution equal to their current_value.
    """
    holdings_rows = get_db().execute("SELECT * FROM holdings").fetchall()

    # DB total matches the dashboard exactly
    db_total = sum(h["current_value"] for h in holdings_rows)

    # Tickers that have at least one cash-type entry (e.g. money market funds like
    # SPAXX) must be treated entirely as constant-value, even if a separate sell
    # transaction was recorded with a different asset_type.
    cash_tickers: set[str] = set()
    for h in holdings_rows:
        t = (h["ticker"] or "").strip().upper()
        if t and t != "$$CASH" and h["asset_type"] == "cash":
            cash_tickers.add(t)

    current_value_by_ticker: dict[str, float] = {}
    for h in holdings_rows:
        t = (h["ticker"] or "").strip().upper()
        if t and t != "$$CASH":
            current_value_by_ticker[t] = current_value_by_ticker.get(t, 0.0) + h["current_value"]

    shares_by_ticker: dict[str, float] = {}
    constant_value = 0.0

    for h in holdings_rows:
        ticker = (h["ticker"] or "").strip().upper()
        if not ticker or ticker == "$$CASH" or h["asset_type"] == "cash" or ticker in cash_tickers:
            constant_value += h["current_value"]
            continue
        shares_by_ticker[ticker] = shares_by_ticker.get(ticker, 0.0) + h["shares"]

    # Drop closed / rounding-dust positions. Share residuals after sell-all can be
    # larger than float eps (e.g. BIL left with ~-5e-5 shares and ~$0 value) and
    # would otherwise appear as a phantom series that charts as -100%.
    shares_by_ticker = {
        t: s
        for t, s in shares_by_ticker.items()
        if abs(s) >= 1e-9
        and abs(current_value_by_ticker.get(t, 0.0)) > NEGLIGIBLE_VALUE
    }

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=375)  # a little extra so we can trim to 365

    if not shares_by_ticker:
        return {
            "dates": [],
            "values": [],
            "summary": {},
            "untracked": [],
            "untracked_value": round(constant_value, 2),
        }

    tickers_list = list(shares_by_ticker.keys())
    raw = yf.download(
        tickers_list,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        multi_level_index=True,
    )

    if raw.empty:
        return {
            "dates": [],
            "values": [],
            "summary": {},
            "untracked": tickers_list,
            "untracked_value": round(constant_value, 2),
        }

    close = raw["Close"]  # DataFrame: index=Date, columns=tickers

    portfolio = pd.Series(0.0, index=close.index)
    untracked = []
    for ticker, shares in shares_by_ticker.items():
        if ticker in close.columns and not close[ticker].isna().all():
            portfolio = portfolio + close[ticker].ffill().fillna(0) * shares
        else:
            untracked.append(ticker)
            constant_value += current_value_by_ticker.get(ticker, 0.0)

    portfolio = portfolio + constant_value
    portfolio = portfolio.dropna()

    cutoff = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    portfolio = portfolio[portfolio.index >= cutoff]

    if portfolio.empty:
        return {
            "dates": [],
            "values": [],
            "summary": {},
            "untracked": untracked,
            "untracked_value": round(constant_value, 2),
        }

    dates = [d.strftime("%Y-%m-%d") for d in portfolio.index]
    values = [round(float(v), 2) for v in portfolio.values]

    ticker_names: dict[str, str] = {}
    for h in holdings_rows:
        tkr = (h["ticker"] or "").strip().upper()
        if tkr and tkr not in ticker_names:
            ticker_names[tkr] = h["name"] or tkr

    holdings_series = []
    for ticker, shares in shares_by_ticker.items():
        if ticker not in close.columns:
            continue
        series = (close[ticker].ffill() * shares).reindex(portfolio.index).ffill().fillna(0)
        h_values = [round(float(v), 2) for v in series.values]
        # Skip series that never rise above dust (defensive; value filter above
        # should already exclude these).
        if not h_values or max(abs(v) for v in h_values) <= NEGLIGIBLE_VALUE:
            continue
        holdings_series.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ticker),
            "values": h_values,
        })
    holdings_series.sort(key=lambda x: x["values"][-1] if x["values"] else 0, reverse=True)

    ticker_asset_type: dict[str, str] = {}
    for h in holdings_rows:
        tkr = (h["ticker"] or "").strip().upper()
        if tkr and tkr not in ticker_asset_type:
            ticker_asset_type[tkr] = h["asset_type"] or ""

    tracked_tickers = [h["ticker"] for h in holdings_series]
    with ThreadPoolExecutor(max_workers=6) as _pool:
        _futures = {
            _pool.submit(get_ticker_category, t, ticker_asset_type.get(t, "")): t
            for t in tracked_tickers
        }
        ticker_categories: dict[str, str] = {}
        for _fut in as_completed(_futures):
            _t = _futures[_fut]
            try:
                ticker_categories[_t] = _fut.result()
            except Exception:
                ticker_categories[_t] = ASSET_TYPE_FALLBACK.get(
                    ticker_asset_type.get(_t, ""), "Other"
                )

    for h_item in holdings_series:
        h_item["category"] = ticker_categories.get(h_item["ticker"], "Other")

    cat_totals: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(dates))
    for h_item in holdings_series:
        cat = h_item["category"]
        for i, v in enumerate(h_item["values"]):
            cat_totals[cat][i] += v

    categories_series = sorted(
        [{"category": cat, "values": [round(v, 2) for v in vals]} for cat, vals in cat_totals.items()],
        key=lambda x: x["values"][-1] if x["values"] else 0,
        reverse=True,
    )

    start_val = values[0]
    peak_val = max(max(values), db_total)
    trough = min(values)

    portfolio.index = pd.to_datetime(portfolio.index)
    monthly_first = portfolio.resample("MS").first()
    monthly_last = portfolio.resample("MS").last()
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

    db_gain = db_total - start_val
    db_gain_pct = (db_gain / start_val * 100) if start_val else 0

    return {
        "dates": dates,
        "values": values,
        "summary": {
            "start_value": round(start_val, 2),
            "end_value": round(db_total, 2),  # matches dashboard
            "gain": round(db_gain, 2),
            "gain_pct": round(db_gain_pct, 2),
            "peak_value": round(peak_val, 2),
            "trough_value": round(trough, 2),
        },
        "monthly": monthly,
        "holdings_series": holdings_series,
        "categories_series": categories_series,
        "untracked": untracked,
        "untracked_value": round(constant_value, 2),
    }

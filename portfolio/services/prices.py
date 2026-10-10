"""Bulk price refresh against yfinance."""

from __future__ import annotations

import threading
from datetime import datetime

import yfinance as yf

from portfolio.db import get_db
from portfolio.services.audit import get_app_logger
from portfolio.services.snapshots import capture_snapshot

_refresh_lock = threading.Lock()


def refresh_all_prices() -> dict:
    """Update current_value for every holding that has a ticker.

    Serializes overlapping manual and scheduled refreshes so two yfinance
    sweeps cannot interleave writes to the same rows.
    """
    with _refresh_lock:
        return _refresh_all_prices_unlocked()


def _fetch_price_and_category(symbol: str) -> tuple[float | None, str]:
    """One Yahoo lookup for a symbol. Category is returned but not required."""
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    price = info.get("regularMarketPrice")
    if price is None:
        try:
            price = ticker.fast_info.last_price
        except Exception:
            price = None
    category = info.get("category") or info.get("sector") or ""
    return price, category


def _refresh_all_prices_unlocked() -> dict:
    db = get_db()
    holdings = db.execute(
        "SELECT * FROM holdings WHERE ticker != ''"
    ).fetchall()

    updated, skipped, errors = [], [], []
    now = datetime.utcnow().isoformat()
    _app_logger = get_app_logger()

    # One lookup per symbol, then apply that price to every lot. A set category
    # is left alone so a refresh cannot move a holding between rebalance buckets.
    grouped: dict[str, list] = {}
    for h in holdings:
        symbol = (h["ticker"] or "").strip().upper()
        if symbol == "$$CASH":
            db.execute(
                "UPDATE holdings SET current_value=shares, updated_at=? WHERE id=?",
                (now, h["id"]),
            )
            updated.append(symbol)
            continue
        grouped.setdefault(symbol, []).append(h)

    for symbol, rows in grouped.items():
        try:
            price, fetched_category = _fetch_price_and_category(symbol)
        except Exception as exc:
            _app_logger.error("refresh_prices %s: %s", symbol, exc)
            errors.append({"ticker": symbol, "error": "Unable to fetch price data"})
            continue
        if price is None:
            skipped.append(symbol)
            continue
        for h in rows:
            stored = (h["category"] or "").strip()
            category = stored or fetched_category or ""
            new_value = round(h["shares"] * price, 2)
            if not stored and fetched_category:
                db.execute(
                    """UPDATE holdings
                       SET current_value=?, category=?, updated_at=?
                       WHERE id=?""",
                    (new_value, fetched_category, now, h["id"]),
                )
            else:
                db.execute(
                    "UPDATE holdings SET current_value=?, updated_at=? WHERE id=?",
                    (new_value, now, h["id"]),
                )
            updated.append({
                "ticker": symbol,
                "price": price,
                "new_value": new_value,
                "category": category,
            })

    db.commit()

    try:
        capture_snapshot()
    except Exception as exc:
        _app_logger.error("capture_snapshot after refresh: %s", exc)

    return {"updated": updated, "skipped": skipped, "errors": errors}

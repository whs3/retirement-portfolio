"""Bulk price refresh against yfinance."""

from __future__ import annotations

import threading
from datetime import datetime

import yfinance as yf

from portfolio.db import get_db
from portfolio.services.audit import audit, get_app_logger
from portfolio.services.snapshots import capture_snapshot

_refresh_lock = threading.Lock()


def refresh_all_prices() -> dict:
    """Update current_value for every holding that has a ticker.

    Serializes overlapping manual and scheduled refreshes so two yfinance
    sweeps cannot interleave writes to the same rows.
    """
    with _refresh_lock:
        return _refresh_all_prices_unlocked()


def _refresh_all_prices_unlocked() -> dict:
    db = get_db()
    holdings = db.execute(
        "SELECT * FROM holdings WHERE ticker != ''"
    ).fetchall()

    updated, skipped, errors = [], [], []
    now = datetime.utcnow().isoformat()
    _app_logger = get_app_logger()

    for h in holdings:
        if h["ticker"].upper() == "$$CASH":
            db.execute(
                "UPDATE holdings SET current_value=shares, updated_at=? WHERE id=?",
                (now, h["id"]),
            )
            updated.append(h["ticker"])
            continue
        try:
            t = yf.Ticker(h["ticker"])
            info = t.info
            price = info.get("regularMarketPrice") or t.fast_info.last_price
            if price is None:
                skipped.append(h["ticker"])
                continue
            category = info.get("category") or info.get("sector") or h["category"]
            new_value = round(h["shares"] * price, 2)
            db.execute(
                "UPDATE holdings SET current_value=?, category=?, updated_at=? WHERE id=?",
                (new_value, category, now, h["id"]),
            )
            audit(
                "PRICE_UPDATE",
                h["ticker"],
                h["name"],
                old_value=h["current_value"],
                new_value=new_value,
                price=price,
            )
            updated.append({
                "ticker": h["ticker"],
                "price": price,
                "new_value": new_value,
                "category": category,
            })
        except Exception as exc:
            _app_logger.error("refresh_prices %s: %s", h["ticker"], exc)
            errors.append({"ticker": h["ticker"], "error": "Unable to fetch price data"})

    db.commit()

    try:
        capture_snapshot()
    except Exception as exc:
        _app_logger.error("capture_snapshot after refresh: %s", exc)

    return {"updated": updated, "skipped": skipped, "errors": errors}

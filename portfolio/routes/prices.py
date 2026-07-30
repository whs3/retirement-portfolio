"""Live price fetch and bulk refresh API."""

from datetime import datetime

import yfinance as yf
from flask import Blueprint, jsonify

from portfolio.db import get_db
from portfolio.extensions import limiter
from portfolio.services.audit import audit, get_app_logger
from portfolio.validators import VALID_TICKER

bp = Blueprint("prices", __name__)


@bp.route("/api/price/<ticker>")
def get_price(ticker):
    symbol = ticker.strip().upper()
    if symbol == "$$CASH":
        return jsonify({"price": 1.0, "name": "Cash", "category": "Cash"})
    if not VALID_TICKER.match(symbol):
        return jsonify({"error": "Invalid ticker format"}), 400
    _app_logger = get_app_logger()
    try:
        t = yf.Ticker(symbol)
        info = t.info
        price = info.get("regularMarketPrice") or t.fast_info.last_price
        if price is None:
            return jsonify({"error": "Price unavailable"}), 404
        name = info.get("longName") or info.get("shortName")
        category = info.get("category") or info.get("sector") or ""
        return jsonify({
            "ticker": symbol,
            "price": price,
            "name": name,
            "category": category,
        })
    except Exception as exc:
        _app_logger.error("get_price %s: %s", symbol, exc)
        return jsonify({
            "error": f"Ticker '{symbol}' not found or data unavailable"
        }), 502


@bp.route("/api/holdings/refresh-prices", methods=["POST"])
@limiter.limit("10 per minute")
def refresh_prices():
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
    return jsonify({"updated": updated, "skipped": skipped, "errors": errors})

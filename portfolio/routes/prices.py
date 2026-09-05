"""Live price fetch and bulk refresh API."""

import yfinance as yf
from flask import Blueprint, jsonify

from portfolio.extensions import limiter
from portfolio.services.audit import get_app_logger
from portfolio.services.prices import refresh_all_prices
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
    return jsonify(refresh_all_prices())

"""Morningstar category / sector lookups with in-process cache."""

import yfinance as yf

# Category cache: avoids re-fetching on every performance page load within a server session
_category_cache: dict[str, str] = {}

ASSET_TYPE_FALLBACK = {
    "stock": "Other Stock",
    "bond": "Other Bond",
    "etf": "Other",
    "mutual_fund": "Other",
}


def get_ticker_category(ticker: str, asset_type: str) -> str:
    """Return the Morningstar category (ETF/fund) or sector (stock) for a ticker."""
    if ticker in _category_cache:
        return _category_cache[ticker]
    cat = None
    try:
        info = yf.Ticker(ticker).info
        qt = (info.get("quoteType") or "").lower()
        if qt in ("etf", "mutualfund"):
            cat = (info.get("category") or "").strip() or None
        else:
            cat = (info.get("sector") or "").strip() or None
    except Exception:
        pass
    # Only cache a successful lookup; failed lookups retry on the next request
    if cat:
        _category_cache[ticker] = cat
        return cat
    # Fallback: don't use asset_type labels like "ETF" — they're not meaningful categories
    return ASSET_TYPE_FALLBACK.get(asset_type, "Other")

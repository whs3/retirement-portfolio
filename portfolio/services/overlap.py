"""Portfolio stock-level overlap analysis across ETFs and individual holdings."""

from portfolio.db import get_db
from portfolio.services.audit import get_app_logger
from portfolio.services.etf_holdings import (
    BOND_ETF_TICKERS,
    SOURCE_LABELS,
    get_etf_holdings,
)
from portfolio.services.settings import get_fmp_api_key


def build_overlap() -> dict:
    """
    Break every holding down to its underlying individual stocks and accumulate
    the dollar value of each stock across the whole portfolio.

    - stock       → counted at full current_value
    - etf / mutual_fund → top holdings fetched via providers/yfinance; remainder
                          bucketed as "Other Holdings"
    - bond        → counted as-is under Bond / Fixed Income
    - cash        → excluded
    """
    holdings_rows = get_db().execute("SELECT * FROM holdings").fetchall()
    _app_logger = get_app_logger()

    summarised: dict[str, dict] = {}  # ticker/key → {name, asset_type, value}
    for h in holdings_rows:
        if h["asset_type"] == "cash":
            continue
        key = (h["ticker"] or h["name"]).upper()
        if key not in summarised:
            summarised[key] = {
                "name": h["name"],
                "asset_type": h["asset_type"],
                "value": 0.0,
            }
        summarised[key]["value"] += h["current_value"]

    fmp_api_key = get_fmp_api_key()

    stock_totals: dict[str, dict] = {}  # key → {name, value}
    other_value = 0.0
    other_breakdown: list[dict] = []
    bond_fi_value = 0.0
    errors = []

    def _add(key: str, name: str, value: float):
        if key not in stock_totals:
            stock_totals[key] = {"name": name, "value": 0.0}
        stock_totals[key]["value"] += value

    for ticker, info in summarised.items():
        asset_type = info["asset_type"]
        total_value = info["value"]

        if asset_type == "stock":
            _add(ticker, info["name"], total_value)

        elif asset_type in ("etf", "mutual_fund"):
            if ticker in BOND_ETF_TICKERS:
                bond_fi_value += total_value
                continue

            try:
                holdings, source = get_etf_holdings(ticker, fmp_api_key)

                total_pct = 0.0
                for h in holdings:
                    total_pct += h["weight"]
                    _add(h["symbol"], h["name"], total_value * h["weight"])

                remaining = max(0.0, 1.0 - total_pct)
                remainder_value = total_value * remaining
                other_value += remainder_value
                if remainder_value > 0.01:
                    other_breakdown.append({
                        "ticker": ticker,
                        "name": info["name"],
                        "covered_pct": round(total_pct * 100, 1),
                        "other_pct": round(remaining * 100, 1),
                        "other_value": round(remainder_value, 2),
                        "source": SOURCE_LABELS.get(source, source),
                    })

            except Exception as exc:
                _app_logger.error("overlap %s: %s", ticker, exc)
                errors.append({"ticker": ticker, "error": "Unable to fetch holdings data"})
                bond_fi_value += total_value

        elif asset_type == "bond":
            bond_fi_value += total_value

    if bond_fi_value > 0.01:
        _add("__BOND_FI__", "Bond / Fixed Income", bond_fi_value)
    if other_value > 0.01:
        _add("__OTHER__", "Other Holdings", other_value)

    result = [
        {"ticker": k, "name": v["name"], "value": round(v["value"], 2)}
        for k, v in stock_totals.items()
    ]
    result.sort(key=lambda x: x["value"], reverse=True)

    total = sum(r["value"] for r in result)
    for r in result:
        r["percentage"] = round((r["value"] / total * 100) if total else 0, 2)

    other_breakdown.sort(key=lambda x: x["other_value"], reverse=True)
    return {
        "stocks": result,
        "total": round(total, 2),
        "errors": errors,
        "other_breakdown": other_breakdown,
    }

"""Ticker lookup: price history, fund info, analyst data."""

from datetime import datetime

import yfinance as yf

from portfolio.services.audit import get_app_logger
from portfolio.services.etf_holdings import get_etf_holdings
from portfolio.services.fund_index import extract_fund_index
from portfolio.services.settings import get_fmp_api_key
from portfolio.validators import VALID_TICKER


def lookup_ticker_data(ticker: str) -> tuple[dict | None, int, str | None]:
    """
    Build lookup payload for a ticker.

    Returns (payload, http_status, error_message).
    On success error_message is None and payload is the response body.
    """
    symbol = ticker.strip().upper()
    if not VALID_TICKER.match(symbol):
        return None, 400, "Invalid ticker format"

    _app_logger = get_app_logger()
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1y")
        if hist.empty:
            return None, 404, f"No price history found for '{symbol}'"

        info = t.info
        name = info.get("longName") or info.get("shortName") or symbol
        quote_type = (info.get("quoteType") or "").lower()

        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        prices = [round(float(p), 2) for p in hist["Close"]]

        start_price = prices[0]
        current_price = prices[-1]
        change = current_price - start_price
        change_pct = (change / start_price * 100) if start_price else 0

        top_holdings = []
        if quote_type in ("etf", "mutualfund"):
            try:
                holdings, _ = get_etf_holdings(symbol, get_fmp_api_key())
                for h in holdings[:10]:
                    top_holdings.append({
                        "symbol": h["symbol"],
                        "name": h["name"],
                        "weight": round(h["weight"] * 100, 2),
                    })
            except Exception:
                try:
                    top = t.funds_data.top_holdings
                    if top is not None and not top.empty:
                        for sym, row in top.head(10).iterrows():
                            top_holdings.append({
                                "symbol": str(sym),
                                "name": str(row["Name"]),
                                "weight": round(float(row["Holding Percent"]) * 100, 2),
                            })
                except Exception:
                    pass

        fund_info = {}
        if quote_type in ("etf", "mutualfund"):
            desc = (info.get("longBusinessSummary") or "")[:500] or None

            ytd_return_calc = None
            try:
                import datetime as _dt

                year_start = str(_dt.date.today().year) + "-01-01"
                ytd_hist = hist[hist.index >= year_start]
                if not ytd_hist.empty:
                    ytd_first = float(ytd_hist["Close"].iloc[0])
                    if ytd_first:
                        ytd_return_calc = round(
                            (current_price - ytd_first) / ytd_first * 100, 4
                        )
            except Exception:
                pass

            benchmark_info = extract_fund_index(desc or "")
            if benchmark_info.get("ticker") and benchmark_info["ticker"] != symbol:
                try:
                    idx_hist = yf.Ticker(benchmark_info["ticker"]).history(period="1y")
                    if not idx_hist.empty:
                        idx_prices = idx_hist["Close"].dropna()
                        idx_current = float(idx_prices.iloc[-1])
                        benchmark_info["one_year_return"] = round(
                            (idx_current - float(idx_prices.iloc[0]))
                            / float(idx_prices.iloc[0])
                            * 100,
                            4,
                        )
                        year_start = str(datetime.now().year) + "-01-01"
                        idx_ytd = idx_hist[idx_hist.index >= year_start]["Close"].dropna()
                        if not idx_ytd.empty:
                            benchmark_info["ytd_return"] = round(
                                (idx_current - float(idx_ytd.iloc[0]))
                                / float(idx_ytd.iloc[0])
                                * 100,
                                4,
                            )
                except Exception:
                    pass

            fund_info = {
                "fund_family": info.get("fundFamily"),
                "category": info.get("category"),
                "total_assets": info.get("totalAssets"),
                "expense_ratio": info.get("netExpenseRatio"),
                "ytd_return": ytd_return_calc,
                "three_year_return": info.get("threeYearAverageReturn"),
                "five_year_return": info.get("fiveYearAverageReturn"),
                "description": desc,
                "benchmark": benchmark_info,
            }

        analyst = {}
        rec_key = (info.get("recommendationKey") or "").lower().replace(" ", "")
        if rec_key and rec_key != "none":
            analyst["recommendation"] = rec_key
            analyst["recommendation_mean"] = info.get("recommendationMean")
            analyst["num_analysts"] = info.get("numberOfAnalystOpinions")
            analyst["target_mean"] = info.get("targetMeanPrice")
            analyst["target_high"] = info.get("targetHighPrice")
            analyst["target_low"] = info.get("targetLowPrice")

            recent_actions = []
            try:
                ud = t.upgrades_downgrades
                if ud is not None and not ud.empty:
                    for idx, row in ud.head(6).iterrows():
                        recent_actions.append({
                            "date": str(idx)[:10],
                            "firm": str(row.get("Firm", "")),
                            "from_grade": str(row.get("FromGrade", "")),
                            "to_grade": str(row.get("ToGrade", "")),
                            "action": str(
                                row.get("priceTargetAction", row.get("Action", ""))
                            ),
                            "price_target": row.get("currentPriceTarget"),
                        })
            except Exception:
                pass
            analyst["recent_actions"] = recent_actions

        payload = {
            "symbol": symbol,
            "name": name,
            "quote_type": quote_type,
            "dates": dates,
            "prices": prices,
            "current_price": round(current_price, 2),
            "start_price": round(start_price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
            "top_holdings": top_holdings,
            "analyst": analyst,
            "fund_info": fund_info,
        }
        return payload, 200, None
    except Exception as exc:
        _app_logger.error("lookup_ticker %s: %s", symbol, exc)
        return None, 502, f"Unable to fetch data for '{symbol}'"

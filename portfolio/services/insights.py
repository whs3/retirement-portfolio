"""Market snapshot and analyst-driven portfolio insights."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import yfinance as yf

from portfolio.db import get_db
from portfolio.validators import NEGLIGIBLE_VALUE


def get_market_snapshot():
    """Return a small list of market index snapshots (price + recent daily change %)."""
    symbols = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ Composite",
        "^VIX": "VIX (Volatility)",
    }
    results = []
    for sym, label in symbols.items():
        try:
            t = yf.Ticker(sym)
            info = t.info
            price = info.get("regularMarketPrice") or t.fast_info.last_price
            prev = info.get("regularMarketPreviousClose") or price
            chg = None
            if price and prev and prev != 0:
                chg = round((price - prev) / prev * 100, 2)
            results.append({
                "symbol": sym,
                "name": label,
                "price": round(price, 2) if price else None,
                "change_pct": chg,
            })
        except Exception:
            results.append({
                "symbol": sym,
                "name": label,
                "price": None,
                "change_pct": None,
            })
    return results


def get_analyst_snapshot(ticker: str) -> dict:
    """Fetch minimal analyst + pricing info for a ticker (used by /api/insights)."""
    sym = (ticker or "").strip().upper()
    if not sym or sym == "$$CASH":
        return {"has_analyst": False}

    try:
        t = yf.Ticker(sym)
        info = t.info
        price = info.get("regularMarketPrice") or info.get("currentPrice") or t.fast_info.last_price

        rec_key = (info.get("recommendationKey") or "").lower().replace(" ", "")
        mean = info.get("recommendationMean")
        num = info.get("numberOfAnalystOpinions")
        tgt_mean = info.get("targetMeanPrice")

        upside = None
        if price and tgt_mean:
            try:
                upside = round((tgt_mean - price) / price * 100, 1)
            except Exception:
                upside = None

        has = bool(rec_key and rec_key not in ("", "none") and mean is not None)

        analyst = {
            "has_analyst": has,
            "current_price": round(price, 2) if price else None,
            "recommendation": rec_key if has else None,
            "recommendation_mean": mean,
            "num_analysts": num,
            "target_mean": round(tgt_mean, 2) if tgt_mean else None,
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "upside_pct": upside,
            "sector": info.get("sector") or info.get("category") or "",
        }

        # Fund / ETF characteristics
        expense = info.get("netExpenseRatio") or info.get("expenseRatio")
        aum = info.get("totalAssets") or info.get("netAssets")
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        div_yld = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        beta = info.get("beta3Year")
        cat = info.get("category")

        fund = {}
        if expense is not None:
            fund["expense_ratio"] = round(expense, 4)
        if aum is not None:
            fund["aum"] = aum
        if pe is not None:
            fund["trailing_pe"] = round(pe, 2)
        if pb is not None:
            fund["price_to_book"] = round(pb, 2)
        if div_yld is not None:
            fund["dividend_yield"] = round(div_yld * 100, 2) if div_yld < 1 else round(div_yld, 2)
        if beta is not None:
            fund["beta_3y"] = round(beta, 2)
        if cat:
            fund["category"] = cat

        return {**analyst, "fund": fund}
    except Exception:
        return {"has_analyst": False, "error": True, "fund": {}}


def build_insights() -> dict:
    """Analyze current holdings using analyst consensus and price targets."""
    holdings_rows = get_db().execute("SELECT * FROM holdings").fetchall()

    total_value = sum(h["current_value"] for h in holdings_rows)

    market_snapshot = get_market_snapshot()

    # Aggregate by ticker (analyst data is per symbol, not per account/owner row)
    ticker_value: dict[str, dict] = {}
    for h in holdings_rows:
        t = (h["ticker"] or "").strip().upper()
        key = t if t and t != "$$CASH" else f"__NOTICKER_{h['id']}"
        if key not in ticker_value:
            ticker_value[key] = {
                "ticker": t if t and t != "$$CASH" else "",
                "name": h["name"],
                "asset_type": h["asset_type"],
                "current_value": 0.0,
            }
        ticker_value[key]["current_value"] += h["current_value"]

    # Drop fully-sold / rounding-dust positions (e.g. BNDX left at ~$0.01 after
    # sell-all). Compare on rounded cents so float residuals that display as
    # $0.01 are excluded and never trigger Yahoo fetches.
    ticker_value = {
        k: v
        for k, v in ticker_value.items()
        if abs(round(v["current_value"], 2)) > NEGLIGIBLE_VALUE
    }

    analyst_results: dict[str, dict] = {}
    fetch_tickers = [k for k, v in ticker_value.items() if v["ticker"] and v["ticker"] != "$$CASH"]

    if fetch_tickers:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(get_analyst_snapshot, tk): tk for tk in fetch_tickers}
            for fut in as_completed(futures):
                tk = futures[fut]
                try:
                    analyst_results[tk] = fut.result()
                except Exception:
                    analyst_results[tk] = {"has_analyst": False}

    holdings_out = []
    covered_value = 0.0
    upside_weighted_sum = 0.0
    upside_weight_sum = 0.0
    sentiment: dict[str, float] = {}
    analyst_ticker_count = 0

    for key, tv in ticker_value.items():
        tkr = tv["ticker"]
        val = tv["current_value"]
        a = analyst_results.get(tkr, {}) if tkr else {}
        fund = (a or {}).pop("fund", {}) if isinstance(a, dict) else {}

        row = {
            "ticker": tkr or "",
            "name": tv["name"],
            "current_value": round(val, 2),
            "analyst": a if a else {"has_analyst": False},
            "fund": fund,
        }

        if a.get("has_analyst"):
            covered_value += val
            analyst_ticker_count += 1

            up = a.get("upside_pct")
            if up is not None:
                upside_weighted_sum += up * val
                upside_weight_sum += val

            r = a.get("recommendation") or "none"
            sentiment[r] = sentiment.get(r, 0.0) + val

            mean = a.get("recommendation_mean") or 3.0
            up = a.get("upside_pct")
            action = "Monitor"
            action_code = "monitor"
            if up is not None and up >= 10 and mean <= 2.5:
                action = "Consider adding"
                action_code = "add"
            elif (mean >= 3.5) or (up is not None and up <= -5):
                action = "Consider trimming"
                action_code = "trim"
            row["action"] = action
            row["action_code"] = action_code
        else:
            if tv.get("asset_type") in ("bond", "cash") or not tkr:
                row["action"] = "Hold (no equity analyst coverage)"
                row["action_code"] = "monitor"
            else:
                row["action"] = "Monitor (limited analyst data)"
                row["action_code"] = "monitor"

        holdings_out.append(row)

    holdings_out = [
        h for h in holdings_out
        if abs(round(h.get("current_value", 0), 2)) > NEGLIGIBLE_VALUE
    ]
    holdings_out.sort(key=lambda x: x["current_value"], reverse=True)

    avg_upside = (upside_weighted_sum / upside_weight_sum) if upside_weight_sum > 0 else None

    rating_order = ["strong_buy", "buy", "hold", "sell", "strong_sell", "none"]
    sentiment_breakdown = []
    for r in rating_order:
        if r in sentiment:
            sentiment_breakdown.append({
                "rating": r,
                "value": round(sentiment[r], 2),
            })
    for r, v in sorted(sentiment.items(), key=lambda x: -x[1]):
        if r not in rating_order:
            sentiment_breakdown.append({"rating": r, "value": round(v, 2)})

    total_equity_like = 0.0
    expense_weighted = 0.0
    expense_weight = 0.0
    pe_weighted = 0.0
    pe_weight = 0.0
    high_expense_value = 0.0
    high_expense_count = 0

    for h in holdings_out:
        val = h["current_value"]
        f = h.get("fund") or {}
        exp = f.get("expense_ratio")
        pe = f.get("trailing_pe")
        asset = tv.get("asset_type") if (tv := ticker_value.get(h["ticker"])) else ""

        if exp is not None:
            expense_weighted += exp * val
            expense_weight += val
            if exp > 0.15:  # > 0.15%
                high_expense_value += val
                high_expense_count += 1

        if pe is not None and asset in ("stock", "etf", "mutual_fund"):
            pe_weighted += pe * val
            pe_weight += val
            total_equity_like += val

    fund_stats = {}
    if expense_weight > 0:
        fund_stats["weighted_avg_expense"] = round(expense_weighted / expense_weight, 3)
    if pe_weight > 0:
        fund_stats["weighted_avg_pe"] = round(pe_weighted / pe_weight, 2)
    if total_equity_like > 0:
        fund_stats["equity_value_with_pe"] = round(total_equity_like, 2)
    fund_stats["high_expense_value"] = round(high_expense_value, 2)
    fund_stats["high_expense_count"] = high_expense_count

    recommendations = []

    if avg_upside is not None:
        sign = "positive" if avg_upside >= 0 else "negative"
        recommendations.append(
            f"Analyst consensus implies an average {sign} upside of {abs(avg_upside):.1f}% "
            f"across analyst-covered holdings."
        )

    buy_value = sum(b["value"] for b in sentiment_breakdown if b["rating"] in ("strong_buy", "buy"))
    sell_value = sum(b["value"] for b in sentiment_breakdown if b["rating"] in ("sell", "strong_sell"))
    if buy_value > total_value * 0.15:
        recommendations.append(
            f"{len([h for h in holdings_out if h.get('action_code') == 'add'])} holdings "
            f"currently show strong analyst upside (>10% and Buy/Strong Buy)."
        )
    if sell_value > 0:
        recommendations.append(
            f"You have ${sell_value:,.0f} in holdings with Sell or Strong Sell consensus — "
            f"review these positions."
        )

    if fund_stats.get("weighted_avg_expense"):
        w_exp = fund_stats["weighted_avg_expense"]
        recommendations.append(
            f"Portfolio weighted average expense ratio: {w_exp:.3f}%."
        )
        if w_exp > 0.12:
            recommendations.append(
                f"Your holdings have a relatively high average expense ratio ({w_exp:.3f}%). "
                "Consider lower-cost equivalents in the same categories."
            )

    if fund_stats.get("weighted_avg_pe"):
        w_pe = fund_stats["weighted_avg_pe"]
        if w_pe > 26:
            recommendations.append(
                f"Equity portion shows elevated valuations (weighted avg trailing P/E ≈ {w_pe}). "
                "This may favor tilting toward lower-valuation areas "
                "(value, international, or broad market)."
            )
        elif w_pe < 18:
            recommendations.append(
                f"Equity holdings appear relatively inexpensive on valuation "
                f"(weighted avg P/E ≈ {w_pe})."
            )

    if fund_stats.get("high_expense_value", 0) > total_value * 0.10:
        recommendations.append(
            f"${fund_stats['high_expense_value']:,.0f} is held in funds with expense ratios above ~0.15%."
        )

    adds = [h for h in holdings_out if h.get("action_code") == "add"][:4]
    if adds:
        tickers = ", ".join(h["ticker"] for h in adds if h["ticker"])
        recommendations.append(f"Analyst high-conviction opportunities: {tickers}.")

    trims = [h for h in holdings_out if h.get("action_code") == "trim"][:3]
    if trims:
        tickers = ", ".join(h["ticker"] for h in trims if h["ticker"])
        recommendations.append(f"Consider reviewing or trimming: {tickers}.")

    if total_value > 0 and covered_value / total_value < 0.4:
        recommendations.append(
            "A large portion of your portfolio has limited or no analyst coverage "
            "(ETFs, funds, bonds, or cash). Analyst signals apply only to the covered slice."
        )

    sp = next((x for x in market_snapshot if x["symbol"] == "^GSPC"), None)
    if sp and sp.get("change_pct") is not None:
        direction = "up" if sp["change_pct"] >= 0 else "down"
        recommendations.append(
            f"Market snapshot: S&P 500 {direction} {abs(sp['change_pct']):.2f}% from previous close."
        )

    vix = next((x for x in market_snapshot if x["symbol"] == "^VIX"), None)
    if vix and vix.get("price"):
        vol_note = "low" if vix["price"] < 18 else ("moderate" if vix["price"] < 28 else "elevated")
        recommendations.append(
            f"Current VIX level ({vix['price']:.1f}) indicates {vol_note} market volatility."
        )

    if not recommendations:
        recommendations.append("No strong directional signals from current analyst data.")

    return {
        "market": market_snapshot,
        "portfolio": {
            "total_value": round(total_value, 2),
            "covered_value": round(covered_value, 2),
            "avg_upside_pct": round(avg_upside, 1) if avg_upside is not None else None,
            "num_analyst_holdings": analyst_ticker_count,
            "total_holdings": len(holdings_out),
        },
        "sentiment_breakdown": sentiment_breakdown,
        "fund_stats": fund_stats,
        "holdings": holdings_out,
        "recommendations": recommendations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

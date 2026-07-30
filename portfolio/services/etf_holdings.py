"""ETF / fund underlying holdings from providers, FMP, or yfinance."""

import io

import requests
import yfinance as yf

from portfolio.services.settings import get_fmp_api_key

# Known bond ETF tickers (no equity holdings — route straight to Bond/FI)
BOND_ETF_TICKERS = frozenset({
    "BND", "BNDX", "BNDW", "VGSH", "VGIT", "VGLT", "VMBS", "VTIP", "VTES",
    "SPAB", "SPSB", "SPIB", "SPLB", "SPTI", "SPTL",
    "AGG", "SHY", "IEF", "TLT", "LQD", "HYG", "JNK", "MUB", "TIP",
    "SCHZ", "SCHI",
})

# Ticker → provider map for known ETFs
TICKER_PROVIDER: dict[str, str] = {
    # Vanguard equity
    "VTI": "vanguard", "VOO": "vanguard", "VTV": "vanguard", "VIG": "vanguard",
    "VUG": "vanguard", "VYM": "vanguard", "VGT": "vanguard", "VEA": "vanguard",
    "VWO": "vanguard", "VXUS": "vanguard", "MGK": "vanguard", "MGV": "vanguard",
    "VB": "vanguard", "VO": "vanguard", "VV": "vanguard",
    # State Street (SSGA) equity
    "SPY": "ssga", "SPDW": "ssga", "SPEM": "ssga", "SPLG": "ssga",
    # Invesco
    "QQQ": "invesco", "QQQM": "invesco",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_MAX_XLSX_BYTES = 10 * 1024 * 1024  # 10 MB

SOURCE_LABELS = {
    "vanguard": "Vanguard",
    "ssga": "State Street",
    "invesco": "Invesco",
    "fmp": "FMP",
    "yfinance": "yfinance",
}


def _get_etf_holdings_vanguard(ticker: str) -> list[dict]:
    """Fetch complete holdings from Vanguard's investor API (JSON, paginated)."""
    all_holdings: list[dict] = []
    start, page_size = 0, 1000
    url = (
        f"https://investor.vanguard.com/investment-products/etfs"
        f"/profile/api/{ticker}/portfolio-holding/stock"
    )
    while True:
        resp = requests.get(
            url,
            params={"start": start, "count": page_size},
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"Vanguard API returned {resp.status_code} for {ticker}")
        entities = resp.json().get("fund", {}).get("entity", [])
        for h in entities:
            if h.get("ticker") and h.get("percentWeight") is not None:
                all_holdings.append({
                    "symbol": str(h["ticker"]),
                    "name": h.get("longName", h["ticker"]),
                    "weight": float(h["percentWeight"]) / 100,
                })
        if len(entities) < page_size:
            break
        start += page_size
    if not all_holdings:
        raise ValueError(f"No equity holdings from Vanguard for {ticker}")
    return all_holdings


def _get_etf_holdings_ssga(ticker: str) -> list[dict]:
    """Fetch complete holdings from State Street SSGA (XLSX download)."""
    import openpyxl

    url = (
        f"https://www.ssga.com/us/en/intermediary/etfs/library-content"
        f"/products/fund-data/etfs/us/holdings-daily-us-en-{ticker.lower()}.xlsx"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    if resp.status_code != 200:
        raise ValueError(f"SSGA returned {resp.status_code} for {ticker}")
    if len(resp.content) > _MAX_XLSX_BYTES:
        raise ValueError(f"SSGA file for {ticker} exceeds size limit")

    wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    # Row 5 (index 4) = column headers; rows 6+ = data
    hdr = list(rows[4])
    for col in ("Name", "Ticker", "Weight"):
        if col not in hdr:
            raise ValueError(f"SSGA file for {ticker} missing expected column: {col}")
    name_idx = hdr.index("Name")
    ticker_idx = hdr.index("Ticker")
    weight_idx = hdr.index("Weight")

    result = []
    for row in rows[5:]:
        sym = row[ticker_idx]
        wt = row[weight_idx]
        if sym and wt is not None:
            try:
                result.append({
                    "symbol": str(sym).strip(),
                    "name": str(row[name_idx]).strip() if row[name_idx] else str(sym),
                    "weight": float(wt) / 100,
                })
            except (ValueError, TypeError):
                pass
    if not result:
        raise ValueError(f"No equity holdings from SSGA for {ticker}")
    return result


def _get_etf_holdings_invesco(ticker: str) -> list[dict]:
    """Fetch complete holdings from Invesco's API (JSON)."""
    url = (
        f"https://dng-api.invesco.com/cache/v1/accounts/en_US"
        f"/shareclasses/{ticker}/holdings/fund"
    )
    resp = requests.get(
        url,
        params={"idType": "ticker", "interval": "monthly", "productType": "ETF"},
        headers=_HEADERS,
        timeout=15,
    )
    if resp.status_code != 200:
        raise ValueError(f"Invesco API returned {resp.status_code} for {ticker}")
    holdings = resp.json().get("holdings", [])
    if not holdings:
        raise ValueError(f"No holdings from Invesco for {ticker}")
    return [
        {
            "symbol": h["ticker"],
            "name": h.get("issuerName", h["ticker"]),
            "weight": float(h["percentageOfTotalNetAssets"]) / 100,
        }
        for h in holdings
        if h.get("ticker") and h.get("percentageOfTotalNetAssets") is not None
    ]


def _get_etf_holdings_fmp(ticker: str, api_key: str) -> list[dict]:
    """Fetch full ETF holdings from Financial Modeling Prep (stable endpoint).

    Returns list of {symbol, name, weight} where weight is a decimal (0–1).
    Raises on any failure so the caller can fall back to yfinance.
    """
    url = "https://financialmodelingprep.com/stable/etf/holdings"
    resp = requests.get(url, params={"symbol": ticker, "apikey": api_key}, timeout=10)
    if resp.status_code == 402:
        raise ValueError("FMP plan does not include ETF holdings (paid feature)")
    resp.raise_for_status()
    data = resp.json()
    if not data or isinstance(data, dict):  # error response is a dict
        raise ValueError(data.get("Error Message", "Empty response from FMP"))
    # weightPercentage may be a true percentage (7.12) or decimal (0.0712) depending on plan
    sample_weight = float(data[0].get("weightPercentage") or 0)
    scale = 100.0 if sample_weight > 1.0 else 1.0
    return [
        {
            "symbol": item["asset"],
            "name": item.get("name", item["asset"]),
            "weight": float(item.get("weightPercentage") or 0) / scale,
        }
        for item in data
        if item.get("asset") and item.get("weightPercentage") is not None
    ]


def _get_etf_holdings_yfinance(ticker: str) -> list[dict]:
    """Fetch top ETF holdings from yfinance.

    Returns list of {symbol, name, weight} where weight is a decimal (0–1).
    Raises on any failure.
    """
    top = yf.Ticker(ticker).funds_data.top_holdings
    if top is None or top.empty:
        raise ValueError("No top-holdings data returned")
    return [
        {
            "symbol": str(symbol),
            "name": str(row["Name"]),
            "weight": float(row["Holding Percent"]),
        }
        for symbol, row in top.iterrows()
    ]


_PROVIDER_FETCHERS = {
    "vanguard": _get_etf_holdings_vanguard,
    "ssga": _get_etf_holdings_ssga,
    "invesco": _get_etf_holdings_invesco,
}


def get_etf_holdings(ticker: str, fmp_api_key: str | None = None) -> tuple[list[dict], str]:
    """Return (holdings, source).

    Priority:
      1. Known provider (Vanguard / SSGA / Invesco) — full holdings, free
      2. FMP — full holdings if paid key present
      3. yfinance — top-N holdings fallback
    """
    if fmp_api_key is None:
        fmp_api_key = get_fmp_api_key()

    provider = TICKER_PROVIDER.get(ticker)
    if provider:
        return _PROVIDER_FETCHERS[provider](ticker), provider

    if fmp_api_key:
        try:
            return _get_etf_holdings_fmp(ticker, fmp_api_key), "fmp"
        except Exception:
            pass

    return _get_etf_holdings_yfinance(ticker), "yfinance"

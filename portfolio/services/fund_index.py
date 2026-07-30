"""Extract tracked index name / ticker from fund description text."""

import re

_INDEX_PATTERNS = [
    # "track(s/ing) the performance of (the) X Index"
    re.compile(
        r"track(?:s|ing)?\s+the\s+performance\s+of\s+(?:the\s+)?([^,;(]{4,90}?(?:Index|Indices|Average|Benchmark))",
        re.I,
    ),
    # "replicate(s) (the performance of) (the) X Index"
    re.compile(
        r"replicat(?:e|es|ing)\s+(?:the\s+performance\s+of\s+)?(?:the\s+)?([^,;(]{4,90}?(?:Index|Indices|Average|Benchmark))",
        re.I,
    ),
    # "correspond(s) to (the) X Index"
    re.compile(
        r"correspond\s+to\s+(?:the\s+)?([^,;(]{4,90}?(?:Index|Indices|Average|Benchmark))",
        re.I,
    ),
    # "stocks/securities/assets in the X Index" — avoids matching generic 'in the trust...'
    re.compile(
        r"(?:stocks?|securities?|assets?)\s+in\s+the\s+([A-Z][^,;(]{3,80}?(?:Index|Indices|Benchmark))",
        re.I,
    ),
    # "the X Index, a..." or "the X Index."  — starts with capital letter
    re.compile(
        r"the\s+([A-Z][^,;(]{5,80}?(?:Index|Indices|Benchmark))\s*[,.]",
        re.I,
    ),
    # "invest in the X Index"
    re.compile(
        r"invest\s+in\s+(?:the\s+)?([A-Z][^,;(]{4,80}?(?:Index|Indices|Benchmark))",
        re.I,
    ),
]

_VAGUE_INDEX_NAMES = {
    "the index",
    "index",
    "an index",
    "this index",
    "the applicable index",
    "its index",
    "the applicable benchmark",
    "such index",
    "a benchmark index",
    "performance of the index",
}

# Keyword → yfinance ticker mapping for common indices
_INDEX_TICKER_MAP = [
    (["s&p 500", "standard & poor's 500", "s&p500", "s&p 500 index"], "^GSPC"),
    (["nasdaq-100", "nasdaq 100", "nasdaq100"], "^NDX"),
    (["nasdaq composite"], "^IXIC"),
    (["dow jones industrial", "djia", "dow jones u.s. large-cap value"], "^DJI"),
    (["russell 2000"], "^RUT"),
    (["russell 1000 growth"], "^RLG"),
    (["russell 1000 value"], "^RLV"),
    (["russell 1000"], "^RUI"),
    (["s&p midcap 400", "s&p 400", "s&p mid cap"], "^SP400"),
    (["s&p smallcap 600", "s&p 600"], "^SP600"),
    (["msci eafe"], "EFA"),
    (["msci emerging markets", "ftse emerging markets"], "EEM"),
    (["ftse developed all cap ex u.s", "msci acwi ex u.s"], "VEA"),
    (
        [
            "bloomberg u.s. aggregate",
            "bloomberg barclays u.s. aggregate",
            "barclays u.s. aggregate",
            "bloomberg us aggregate",
        ],
        "AGG",
    ),
    (["bloomberg global aggregate ex-usd"], "BNDX"),
]


def extract_fund_index(description: str) -> dict:
    """
    Return {'name': str, 'ticker': str|None} for the index a fund tracks,
    or {} if no index name can be reliably extracted.
    """
    if not description:
        return {}
    for pat in _INDEX_PATTERNS:
        m = pat.search(description)
        if m:
            raw = re.sub(r"[®™\u00ae\u2122]", "", m.group(1)).strip().rstrip(".,;: ")
            if len(raw) > 90:
                continue
            if raw.lower() in _VAGUE_INDEX_NAMES:
                continue
            if "index" not in raw.lower():
                continue
            # Map to a yfinance ticker if known
            ticker = None
            lower = raw.lower()
            for keywords, idx_ticker in _INDEX_TICKER_MAP:
                if any(kw in lower for kw in keywords):
                    ticker = idx_ticker
                    break
            return {"name": raw, "ticker": ticker}
    return {}

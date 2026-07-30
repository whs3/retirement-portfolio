"""Unit tests for fund index extraction from description text."""

from portfolio.services.fund_index import extract_fund_index


def test_empty_description():
    assert extract_fund_index("") == {}
    assert extract_fund_index(None) == {}


def test_sp500_track_performance():
    desc = (
        "The fund tracks the performance of the S&P 500 Index, a market-cap weighted "
        "index of large U.S. companies."
    )
    result = extract_fund_index(desc)
    assert result["name"]
    assert "S&P 500" in result["name"] or "S&P" in result["name"]
    assert result["ticker"] == "^GSPC"


def test_nasdaq_100():
    desc = "This ETF tracks the performance of the Nasdaq-100 Index."
    result = extract_fund_index(desc)
    assert result.get("ticker") == "^NDX"


def test_vague_index_rejected():
    desc = "The fund tracks the performance of the index."
    # "the index" is vague and should not produce a useful result
    result = extract_fund_index(desc)
    # Either empty or not mapping a vague name as a real index with ticker
    assert result == {} or result.get("ticker") is None


def test_no_index_language():
    desc = "An actively managed large-cap growth equity strategy."
    assert extract_fund_index(desc) == {}


def test_bloomberg_aggregate():
    desc = (
        "The fund seeks to track the performance of the Bloomberg U.S. Aggregate Bond Index."
    )
    result = extract_fund_index(desc)
    assert result.get("ticker") == "AGG"

"""Lookup service tests with yfinance mocked."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from portfolio.services.lookup import lookup_ticker_data


def _hist(days=30, start=100.0):
    dates = pd.bdate_range(end=datetime.now(), periods=days)
    prices = [start + i * 0.5 for i in range(days)]
    return pd.DataFrame({"Close": prices}, index=dates)


def test_lookup_invalid_ticker():
    payload, status, err = lookup_ticker_data("BAD TICKER!")
    assert status == 400
    assert payload is None
    assert "Invalid ticker" in err


def test_lookup_success_stock():
    mock_t = MagicMock()
    mock_t.history.return_value = _hist()
    mock_t.info = {
        "longName": "Apple Inc.",
        "quoteType": "EQUITY",
        "recommendationKey": "buy",
        "recommendationMean": 2.1,
        "numberOfAnalystOpinions": 40,
        "targetMeanPrice": 200,
        "targetHighPrice": 250,
        "targetLowPrice": 150,
        "fiftyTwoWeekHigh": 220,
        "fiftyTwoWeekLow": 140,
    }
    mock_t.upgrades_downgrades = pd.DataFrame()

    with patch("portfolio.services.lookup.yf.Ticker", return_value=mock_t):
        payload, status, err = lookup_ticker_data("AAPL")

    assert err is None
    assert status == 200
    assert payload["symbol"] == "AAPL"
    assert payload["name"] == "Apple Inc."
    assert len(payload["dates"]) == len(payload["prices"])
    assert payload["analyst"]["recommendation"] == "buy"
    assert payload["current_price"] == payload["prices"][-1]


def test_lookup_empty_history():
    mock_t = MagicMock()
    mock_t.history.return_value = pd.DataFrame()

    with patch("portfolio.services.lookup.yf.Ticker", return_value=mock_t):
        payload, status, err = lookup_ticker_data("ZZZZ")

    assert status == 404
    assert payload is None
    assert "No price history" in err

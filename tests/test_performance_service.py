"""Performance service tests with yfinance mocked (no network)."""

from datetime import datetime
from unittest.mock import patch

import pandas as pd

from portfolio.db import get_db
from portfolio.services.performance import build_performance


def _make_price_frame(tickers, days=40, start_price=100.0):
    """Build a multi-level Close frame like yf.download(..., multi_level_index=True)."""
    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = pd.bdate_range(end=end, periods=days)
    data = {}
    for i, tkr in enumerate(tickers):
        # Gentle upward drift so start != end
        prices = [start_price + i * 10 + d * 0.1 for d in range(days)]
        data[("Close", tkr)] = prices
    df = pd.DataFrame(data, index=dates)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def test_performance_empty_portfolio(app_ctx):
    result = build_performance()
    assert result["dates"] == []
    assert result["values"] == []
    assert result["summary"] == {}


def test_performance_cash_only_is_constant(app_ctx):
    """Cash / SPAXX-style holdings contribute constant value, not a price series."""
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "SPAXX", "SPAXX", "cash", "Cash", "Bill", "Broker",
            1000, 1000, 1000, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    # Even if download is never called (no equity tickers), we get empty series
    # with untracked constant — current implementation returns empty dates when
    # shares_by_ticker is empty.
    result = build_performance()
    assert result["dates"] == []
    assert result["untracked_value"] == 1000


def test_performance_with_mocked_download(app_ctx):
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Apple", "AAPL", "stock", "Technology", "Bill", "IRA",
            10, 1000, 1500, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    frame = _make_price_frame(["AAPL"], days=50, start_price=100.0)

    with (
        patch("portfolio.services.performance.yf.download", return_value=frame),
        patch(
            "portfolio.services.performance.get_ticker_category",
            return_value="Technology",
        ),
    ):
        result = build_performance()

    assert len(result["dates"]) > 0
    assert len(result["values"]) == len(result["dates"])
    assert result["summary"]["end_value"] == 1500  # matches DB total
    assert "gain" in result["summary"]
    assert result["holdings_series"]
    assert result["holdings_series"][0]["ticker"] == "AAPL"
    assert result["holdings_series"][0]["category"] == "Technology"
    assert result["categories_series"]
    assert result["monthly"]


def test_performance_cash_ticker_excluded_from_shares(app_ctx):
    """Any ticker with a cash-type row is treated as constant, not priced."""
    db = get_db()
    for row in (
        ("SPAXX MM", "SPAXX", "cash", "Cash", 500, 500, 500),
        # A sell row mistakenly typed as stock should still be constant-path
        ("SPAXX sell", "SPAXX", "stock", "Cash", -100, -100, -100),
    ):
        name, ticker, atype, cat, shares, cost, val = row
        db.execute(
            """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                name, ticker, atype, cat, "Bill", "Broker",
                shares, cost, val, "2024-01-01", "", "2024-01-01", "2024-01-01",
            ),
        )
    db.commit()

    with patch("portfolio.services.performance.yf.download") as mock_dl:
        result = build_performance()
        mock_dl.assert_not_called()

    assert result["dates"] == []
    assert result["untracked_value"] == 400  # 500 + (-100)


def test_performance_zero_net_shares_dropped(app_ctx):
    """Fully offset buy+sell leaves no series and no download for that ticker alone."""
    db = get_db()
    for shares, cost, val in ((10, 1000, 1200), (-10, -1000, -1200)):
        db.execute(
            """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "Apple", "AAPL", "stock", "Technology", "Bill", "IRA",
                shares, cost, val, "2024-01-01", "", "2024-01-01", "2024-01-01",
            ),
        )
    db.commit()

    with patch("portfolio.services.performance.yf.download") as mock_dl:
        result = build_performance()
        mock_dl.assert_not_called()

    assert result["dates"] == []


def test_performance_share_dust_with_zero_value_excluded(app_ctx):
    """Sell residual share dust (e.g. BIL ~-5e-5 shares, $0 value) must not chart.

    The old 1e-9 share threshold let these through; tiny values then rounded and
    normalized to a bogus -100% line on the individual-holdings chart.
    """
    db = get_db()
    # Real open position
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Apple", "AAPL", "stock", "Technology", "Bill", "IRA",
            10, 1000, 1500, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    # Closed BIL-like position: share residual above 1e-9, net value ~0
    for shares, cost, val in (
        (3483.962534, 318956.78, 319305.17),
        (-3483.962582, -318956.78, -319305.17),  # leaves ~-4.8e-5 shares, $0
    ):
        db.execute(
            """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "BIL ETF", "BIL", "etf", "Ultrashort Bond", "Bill", "401k",
                shares, cost, val, "2024-01-01", "", "2024-01-01", "2024-01-01",
            ),
        )
    db.commit()

    frame = _make_price_frame(["AAPL", "BIL"], days=50, start_price=100.0)

    with (
        patch("portfolio.services.performance.yf.download", return_value=frame) as mock_dl,
        patch(
            "portfolio.services.performance.get_ticker_category",
            return_value="Technology",
        ),
    ):
        result = build_performance()

    assert mock_dl.called
    requested = set(mock_dl.call_args.args[0])
    assert requested == {"AAPL"}
    tickers = [h["ticker"] for h in result["holdings_series"]]
    assert tickers == ["AAPL"]

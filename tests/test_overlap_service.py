"""Overlap service tests with ETF holdings mocked (no network)."""

from unittest.mock import patch

from portfolio.db import get_db
from portfolio.services.overlap import build_overlap


def test_overlap_stock_only(app_ctx):
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Apple", "AAPL", "stock", "Technology", "Bill", "IRA",
            10, 1000, 2000, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    result = build_overlap()
    assert result["total"] == 2000
    assert len(result["stocks"]) == 1
    assert result["stocks"][0]["ticker"] == "AAPL"
    assert result["stocks"][0]["percentage"] == 100.0
    assert result["errors"] == []


def test_overlap_etf_expands_holdings(app_ctx):
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Vanguard S&P", "VOO", "etf", "Large Blend", "Bill", "IRA",
            5, 2000, 1000, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    fake_holdings = [
        {"symbol": "AAPL", "name": "Apple", "weight": 0.07},
        {"symbol": "MSFT", "name": "Microsoft", "weight": 0.06},
        {"symbol": "NVDA", "name": "Nvidia", "weight": 0.05},
    ]
    # remaining weight 0.82 → Other Holdings

    with patch(
        "portfolio.services.overlap.get_etf_holdings",
        return_value=(fake_holdings, "yfinance"),
    ):
        result = build_overlap()

    by_ticker = {s["ticker"]: s for s in result["stocks"]}
    assert abs(by_ticker["AAPL"]["value"] - 70) < 0.01
    assert abs(by_ticker["MSFT"]["value"] - 60) < 0.01
    assert "__OTHER__" in by_ticker
    assert result["other_breakdown"]
    assert result["other_breakdown"][0]["ticker"] == "VOO"


def test_overlap_bond_etf_bucketed(app_ctx):
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Agg Bond", "AGG", "etf", "Intermediate Core Bond", "Bill", "IRA",
            10, 1000, 1000, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    with patch("portfolio.services.overlap.get_etf_holdings") as mock_etf:
        result = build_overlap()
        mock_etf.assert_not_called()

    assert result["stocks"][0]["ticker"] == "__BOND_FI__"
    assert result["stocks"][0]["value"] == 1000


def test_overlap_skips_cash(app_ctx):
    db = get_db()
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "Cash", "SPAXX", "cash", "Cash", "Bill", "Broker",
            500, 500, 500, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )
    db.commit()

    result = build_overlap()
    assert result["stocks"] == []
    assert result["total"] == 0

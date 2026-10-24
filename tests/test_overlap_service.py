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


def _insert(db, name, ticker, asset_type, value):
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name, ticker, asset_type, "", "Bill", "IRA",
            1, value, value, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )


def test_overlap_failed_lookup_goes_to_unavailable_not_bond(app_ctx):
    db = get_db()
    _insert(db, "Some Equity ETF", "VTV", "etf", 1000)
    db.commit()

    with patch(
        "portfolio.services.overlap.get_etf_holdings",
        side_effect=ValueError("boom"),
    ):
        result = build_overlap()

    by_ticker = {s["ticker"]: s for s in result["stocks"]}
    assert "__BOND_FI__" not in by_ticker
    assert by_ticker["__UNAVAILABLE__"]["value"] == 1000
    assert result["errors"] == [{"ticker": "VTV", "error": "Unable to fetch holdings data"}]


def test_overlap_skips_non_cash_rows_of_cash_ticker(app_ctx):
    db = get_db()
    _insert(db, "Cash", "SPAXX", "cash", 500)
    _insert(db, "Cash sell", "SPAXX", "etf", -200)
    db.commit()

    with patch("portfolio.services.overlap.get_etf_holdings") as mock_etf:
        result = build_overlap()
        mock_etf.assert_not_called()

    assert result["stocks"] == []
    assert result["errors"] == []


def test_overlap_treasury_bill_etf_is_bond(app_ctx):
    db = get_db()
    _insert(db, "0-3 Month Treasury", "SGOV", "etf", 750)
    db.commit()

    with patch("portfolio.services.overlap.get_etf_holdings") as mock_etf:
        result = build_overlap()
        mock_etf.assert_not_called()

    assert result["stocks"][0]["ticker"] == "__BOND_FI__"
    assert result["stocks"][0]["value"] == 750


def test_get_etf_holdings_falls_back_when_provider_fails():
    from portfolio.services import etf_holdings

    fallback = [{"symbol": "AAPL", "name": "Apple", "weight": 0.07}]
    with patch.dict(
        etf_holdings._PROVIDER_FETCHERS,
        {"vanguard": lambda t: (_ for _ in ()).throw(ValueError("404"))},
    ), patch.object(etf_holdings, "_get_etf_holdings_yfinance", return_value=fallback):
        holdings, source = etf_holdings.get_etf_holdings("VOO", fmp_api_key="")

    assert source == "yfinance"
    assert holdings == fallback

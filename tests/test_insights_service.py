"""Insights service tests with yfinance / analyst calls mocked."""

from unittest.mock import patch

from portfolio.db import get_db
from portfolio.services.insights import build_insights


def _insert(db, *, name, ticker, asset_type, shares, cost, value, owner="Bill"):
    db.execute(
        """INSERT INTO holdings
           (name, ticker, asset_type, category, owner, account_type, shares,
            cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name, ticker, asset_type, "Test", owner, "IRA",
            shares, cost, value, "2024-01-01", "", "2024-01-01", "2024-01-01",
        ),
    )


def test_insights_excludes_negligible_dust_ticker(app_ctx):
    """Sold residual like BNDX at $0.01 must not appear in insights holdings."""
    db = get_db()
    _insert(
        db,
        name="Apple",
        ticker="AAPL",
        asset_type="stock",
        shares=10,
        cost=1000,
        value=1500,
    )
    # Fully sold BNDX-style residual: net shares ~0, net value ~$0.01
    # (matches live portfolio after sell-all rounding)
    _insert(
        db,
        name="BNDX buy",
        ticker="BNDX",
        asset_type="etf",
        shares=1964.697,
        cost=94167.93,
        value=94069.70,
    )
    _insert(
        db,
        name="BNDX sell",
        ticker="BNDX",
        asset_type="etf",
        shares=-1964.697,
        cost=-94167.93,
        value=-94069.69,  # leaves $0.01 dust
    )
    db.commit()

    with (
        patch(
            "portfolio.services.insights.get_market_snapshot",
            return_value=[],
        ),
        patch(
            "portfolio.services.insights.get_analyst_snapshot",
            return_value={"has_analyst": False},
        ) as mock_analyst,
    ):
        result = build_insights()

    tickers = [h["ticker"] for h in result["holdings"]]
    assert "AAPL" in tickers
    assert "BNDX" not in tickers
    # Dust ticker must not trigger an analyst fetch
    fetched = {c.args[0] for c in mock_analyst.call_args_list}
    assert "BNDX" not in fetched
    assert "AAPL" in fetched

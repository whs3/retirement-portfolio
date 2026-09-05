"""Daily snapshot service tests. Only backfill touches yfinance (mocked)."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd

from portfolio.db import get_db
from portfolio.services.snapshots import (
    backfill_once,
    capture_snapshot,
    get_performance_history,
)

TODAY = datetime.utcnow().strftime("%Y-%m-%d")


def _insert(db, **fields):
    defaults = {
        "name": "Apple Inc.", "ticker": "AAPL", "asset_type": "stock",
        "category": "Technology", "owner": "Bill", "account_type": "IRA",
        "shares": 10, "cost_basis": 1000, "current_value": 1500,
        "purchase_date": "2024-01-01", "notes": "",
        "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00",
    }
    defaults.update(fields)
    db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES (:name, :ticker, :asset_type, :category, :owner, :account_type, :shares,
                   :cost_basis, :current_value, :purchase_date, :notes, :created_at, :updated_at)""",
        defaults,
    )
    db.commit()


def _insert_snapshot(db, date, total_value, holdings_json, category_json, untracked_value=0.0):
    db.execute(
        """INSERT INTO portfolio_snapshots
               (date, total_value, total_cost_basis, category_json, holdings_json,
                untracked_value, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (date, total_value, total_value, json.dumps(category_json),
         json.dumps(holdings_json), untracked_value, datetime.utcnow().isoformat()),
    )
    db.commit()


def test_capture_snapshot_creates_row_for_today(app_ctx):
    db = get_db()
    _insert(db)

    capture_snapshot()

    row = db.execute(
        "SELECT * FROM portfolio_snapshots WHERE date = ?", (TODAY,)
    ).fetchone()
    assert row is not None
    assert row["total_value"] == 1500
    assert row["total_cost_basis"] == 1000
    assert json.loads(row["category_json"]) == {"Technology": 1500}
    holdings = json.loads(row["holdings_json"])
    assert holdings["AAPL"]["value"] == 1500
    assert holdings["AAPL"]["category"] == "Technology"


def test_capture_snapshot_upserts_same_day(app_ctx):
    db = get_db()
    _insert(db)
    capture_snapshot()

    db.execute("UPDATE holdings SET current_value = 1800 WHERE ticker = 'AAPL'")
    db.commit()
    capture_snapshot()

    rows = db.execute("SELECT * FROM portfolio_snapshots").fetchall()
    assert len(rows) == 1
    assert rows[0]["total_value"] == 1800


def test_capture_snapshot_excludes_cash_and_dust_from_breakdowns(app_ctx):
    db = get_db()
    _insert(db, name="Apple Inc.", ticker="AAPL", current_value=1500, cost_basis=1000)
    _insert(
        db, name="SPAXX", ticker="SPAXX", asset_type="cash", category="Cash",
        shares=500, cost_basis=500, current_value=500,
    )
    # Dust: fully offset buy/sell pair
    _insert(db, name="Dust Co", ticker="DUST", shares=1, cost_basis=10, current_value=10)
    _insert(db, name="Dust Co", ticker="DUST", shares=-1, cost_basis=-10, current_value=-9.995)

    capture_snapshot()

    row = db.execute(
        "SELECT * FROM portfolio_snapshots WHERE date = ?", (TODAY,)
    ).fetchone()
    # Raw total includes everything, matching the dashboard total exactly.
    assert row["total_value"] == round(1500 + 500 + 10 - 9.995, 2)
    holdings = json.loads(row["holdings_json"])
    assert set(holdings.keys()) == {"AAPL"}
    assert row["untracked_value"] == 500


def test_backfill_noop_when_marker_already_set(app_ctx):
    db = get_db()
    _insert_snapshot(db, "2024-01-01", 1000, {}, {})
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('performance_backfilled_at', 'x')"
    )
    db.commit()

    with patch("portfolio.services.snapshots.build_performance") as mock_bp:
        backfill_once()
        mock_bp.assert_not_called()

    rows = db.execute("SELECT * FROM portfolio_snapshots").fetchall()
    assert len(rows) == 1


def test_backfill_runs_even_if_scheduler_already_captured_today(app_ctx):
    """Regression: the auto-refresh scheduler calls capture_snapshot() on its own
    schedule, independent of backfill. If it beats backfill_once() to the punch
    (writing today's row before anyone hits /api/performance), backfill must
    still run — it used to key off an empty table, which this race permanently
    defeated, leaving Performance stuck on a single day of history."""
    db = get_db()
    _insert(db)
    capture_snapshot()  # simulates the scheduler having already run
    assert db.execute("SELECT COUNT(*) AS c FROM portfolio_snapshots").fetchone()["c"] == 1

    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = pd.bdate_range(end=end, periods=10)

    with patch("portfolio.services.snapshots.build_performance") as mock_bp:
        mock_bp.return_value = {
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "values": [1000.0 + i for i in range(len(dates))],
            "holdings_series": [],
            "categories_series": [],
            "untracked_value": 0.0,
        }
        backfill_once()
        mock_bp.assert_called_once()

    rows = db.execute("SELECT * FROM portfolio_snapshots").fetchall()
    assert len(rows) >= len(dates)


def test_backfill_populates_from_build_performance(app_ctx):
    db = get_db()
    _insert(db)

    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = pd.bdate_range(end=end, periods=10)
    frame = pd.DataFrame({("Close", "AAPL"): [100.0 + d for d in range(len(dates))]}, index=dates)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)

    with (
        patch("portfolio.services.snapshots.build_performance") as mock_bp,
    ):
        mock_bp.return_value = {
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "values": [1000.0 + i for i in range(len(dates))],
            "holdings_series": [
                {"ticker": "AAPL", "name": "Apple Inc.", "category": "Technology",
                 "values": [1000.0 + i for i in range(len(dates))]}
            ],
            "categories_series": [
                {"category": "Technology", "values": [1000.0 + i for i in range(len(dates))]}
            ],
            "untracked_value": 0.0,
        }
        backfill_once()

    rows = db.execute("SELECT * FROM portfolio_snapshots ORDER BY date").fetchall()
    assert len(rows) >= len(dates)
    # Today's row was overwritten with a real, live-computed value afterwards.
    today_row = db.execute(
        "SELECT * FROM portfolio_snapshots WHERE date = ?", (TODAY,)
    ).fetchone()
    assert today_row is not None
    assert today_row["total_value"] == 1500
    marker = db.execute(
        "SELECT value FROM settings WHERE key = 'performance_backfilled_at'"
    ).fetchone()
    assert marker is not None


def test_get_performance_history_shape_from_snapshots_no_network(app_ctx):
    db = get_db()
    base = datetime.utcnow() - timedelta(days=2)
    d0, d1, d2 = [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

    _insert_snapshot(
        db, d0, 1000,
        {"AAPL": {"name": "Apple Inc.", "value": 1000, "category": "Technology"}},
        {"Technology": 1000},
    )
    _insert_snapshot(
        db, d1, 1100,
        {"AAPL": {"name": "Apple Inc.", "value": 1100, "category": "Technology"}},
        {"Technology": 1100},
    )
    _insert_snapshot(
        db, d2, 1200,
        {"AAPL": {"name": "Apple Inc.", "value": 1200, "category": "Technology"}},
        {"Technology": 1200},
        untracked_value=50,
    )

    with patch("portfolio.services.snapshots.build_performance") as mock_bp:
        result = get_performance_history()
        mock_bp.assert_not_called()

    assert result["dates"] == [d0, d1, d2]
    assert result["values"] == [1000, 1100, 1200]
    assert result["summary"]["start_value"] == 1000
    assert result["summary"]["end_value"] == 1200
    assert result["summary"]["gain"] == 200
    assert result["summary"]["peak_value"] == 1200
    assert result["summary"]["trough_value"] == 1000
    assert result["holdings_series"] == [
        {"ticker": "AAPL", "name": "Apple Inc.", "category": "Technology",
         "values": [1000, 1100, 1200]}
    ]
    assert result["categories_series"] == [
        {"category": "Technology", "values": [1000, 1100, 1200]}
    ]
    assert result["untracked_value"] == 50
    assert len(result["monthly"]) >= 1


def test_performance_route_uses_snapshots(client, insert_holding):
    insert_holding(ticker="AAPL", name="Apple Inc.", current_value=1500, cost_basis=1000)

    with patch("portfolio.services.snapshots.build_performance") as mock_bp:
        mock_bp.return_value = {"dates": [], "values": [], "summary": {}}
        res = client.get("/api/performance")

    assert res.status_code == 200
    data = res.get_json()
    assert data["dates"] == [TODAY]
    assert data["values"] == [1500]
    assert data["summary"]["end_value"] == 1500

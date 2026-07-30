"""Shared fixtures for the retirement portfolio test suite."""

from __future__ import annotations

import pytest

from portfolio import create_app
from portfolio.db import get_db


@pytest.fixture
def app(tmp_path):
    """Flask app with isolated SQLite DB and audit log under tmp_path."""
    db_path = tmp_path / "test_portfolio.db"
    audit_path = tmp_path / "test_audit.log"

    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-not-for-production",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "DATABASE": str(db_path),
        "AUDIT_LOG": str(audit_path),
        "TEMPLATES_AUTO_RELOAD": False,
    })
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


def _insert_holding(db, **fields):
    """Insert a holding row with sensible defaults; returns lastrowid."""
    defaults = {
        "name": "Test Holding",
        "ticker": "TEST",
        "asset_type": "stock",
        "category": "Technology",
        "owner": "Bill",
        "account_type": "IRA",
        "shares": 10.0,
        "cost_basis": 1000.0,
        "current_value": 1200.0,
        "purchase_date": "2024-01-15",
        "notes": "",
        "created_at": "2024-01-15T00:00:00",
        "updated_at": "2024-01-15T00:00:00",
    }
    defaults.update(fields)
    cur = db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, category, owner, account_type, shares,
                cost_basis, current_value, purchase_date, notes, created_at, updated_at)
           VALUES
               (:name, :ticker, :asset_type, :category, :owner, :account_type, :shares,
                :cost_basis, :current_value, :purchase_date, :notes, :created_at, :updated_at)""",
        defaults,
    )
    db.commit()
    return cur.lastrowid


@pytest.fixture
def seed_holdings(app):
    """Seed a small, deterministic set of holdings for API tests."""
    with app.app_context():
        db = get_db()
        ids = {
            "aapl": _insert_holding(
                db,
                name="Apple Inc.",
                ticker="AAPL",
                asset_type="stock",
                category="Technology",
                owner="Bill",
                account_type="IRA",
                shares=10,
                cost_basis=1500,
                current_value=2000,
            ),
            "voo": _insert_holding(
                db,
                name="Vanguard S&P 500",
                ticker="VOO",
                asset_type="etf",
                category="Large Blend",
                owner="Akiko",
                account_type="Roth IRA",
                shares=5,
                cost_basis=2000,
                current_value=2500,
            ),
            "bond": _insert_holding(
                db,
                name="US Treasury Bond",
                ticker="",
                asset_type="bond",
                category="Treasury",
                owner="Joint",
                account_type="Broker",
                shares=0,
                cost_basis=5000,
                current_value=5100,
            ),
            "cash": _insert_holding(
                db,
                name="SPAXX",
                ticker="SPAXX",
                asset_type="cash",
                category="Cash",
                owner="Bill",
                account_type="Broker",
                shares=1000,
                cost_basis=1000,
                current_value=1000,
            ),
            # Near-zero net position (sold dust) — should be filtered from summaries
            "dust_buy": _insert_holding(
                db,
                name="Dust Co",
                ticker="DUST",
                asset_type="stock",
                category="Technology",
                owner="Bill",
                account_type="IRA",
                shares=1,
                cost_basis=10,
                current_value=10,
            ),
            "dust_sell": _insert_holding(
                db,
                name="Dust Co",
                ticker="DUST",
                asset_type="stock",
                category="Technology",
                owner="Bill",
                account_type="IRA",
                shares=-1,
                cost_basis=-10,
                current_value=-9.995,  # leaves ~0.005 dust
            ),
        }
        db.execute(
            "INSERT INTO target_allocations (category, target_percentage) VALUES (?, ?)",
            ("Technology", 40),
        )
        db.execute(
            "INSERT INTO target_allocations (category, target_percentage) VALUES (?, ?)",
            ("Large Blend", 30),
        )
        db.execute(
            "INSERT INTO target_allocations (category, target_percentage) VALUES (?, ?)",
            ("Treasury", 20),
        )
        db.execute(
            "INSERT INTO target_allocations (category, target_percentage) VALUES (?, ?)",
            ("Cash", 10),
        )
        db.commit()
        return ids


@pytest.fixture
def insert_holding(app):
    """Callable fixture to insert a custom holding; returns id."""

    def _do(**fields):
        with app.app_context():
            return _insert_holding(get_db(), **fields)

    return _do

"""API tests for GET /api/rmd."""

import json
from datetime import date

from portfolio.db import get_db
from portfolio.timezone_util import today_iso


def _prior_december_31():
    as_of = date.fromisoformat(today_iso())
    return date(as_of.year - 1, 12, 31).isoformat()


def _insert_prior_snapshot(app, owner_accounts):
    """Insert last December 31. ``owner_accounts is None`` leaves the breakdown empty."""
    prior = _prior_december_31()
    with app.app_context():
        db = get_db()
        if owner_accounts is None:
            db.execute(
                """INSERT INTO portfolio_snapshots
                       (date, total_value, total_cost_basis, category_json, holdings_json,
                        untracked_value, created_at)
                   VALUES (?, 1, 0, '{}', '{}', 0, ?)""",
                (prior, "2026-01-01T00:00:00"),
            )
        else:
            db.execute(
                """INSERT INTO portfolio_snapshots
                       (date, total_value, total_cost_basis, category_json, holdings_json,
                        untracked_value, created_at, owner_accounts_json)
                   VALUES (?, 1, 0, '{}', '{}', 0, ?, ?)""",
                (prior, "2026-01-01T00:00:00", json.dumps(owner_accounts)),
            )
        db.commit()
    return prior


def test_no_birthdates_no_holdings(client):
    r = client.get("/api/rmd")
    assert r.status_code == 200
    data = r.get_json()
    owners = {o["owner"]: o for o in data["owners"]}
    assert set(owners) == {"Bill", "Akiko"}
    assert owners["Bill"]["balance"] == 0.0
    assert owners["Bill"]["birthdate"] is None
    assert "required" not in owners["Bill"]


def test_balance_only_sums_rmd_subject_account_types(client, insert_holding):
    insert_holding(owner="Bill", account_type="401k", current_value=100_000)
    insert_holding(owner="Bill", account_type="Rollover IRA", current_value=50_000)
    insert_holding(owner="Bill", account_type="Roth IRA", current_value=999_000)  # excluded
    insert_holding(owner="Joint", account_type="Cash Management", current_value=1_000_000)  # excluded

    r = client.get("/api/rmd")
    data = r.get_json()
    owners = {o["owner"]: o for o in data["owners"]}
    assert owners["Bill"]["balance"] == 150_000.0
    assert owners["Akiko"]["balance"] == 0.0
    assert data["balance_source"] == "current"
    assert "no snapshot" in data["balance_note"]


def test_with_birthdate_includes_rmd_fields(client, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=500_000)
    client.put("/api/settings", json={"birthdate_bill": "1950-01-01"})

    r = client.get("/api/rmd")
    bill = next(o for o in r.get_json()["owners"] if o["owner"] == "Bill")
    assert bill["birthdate"] == "1950-01-01"
    assert bill["required"] is True
    assert bill["rmd_amount"] > 0


def test_december_31_snapshot_is_the_rmd_balance(client, app, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=50_000)
    insert_holding(owner="Akiko", account_type="401k", current_value=1)
    prior = _insert_prior_snapshot(app, {
        "Bill": {"IRA": 265_000, "Roth IRA": 999_000},
        "Akiko": {"403b": 80_000},
        "Joint": {"IRA": 999_000},
    })
    client.put("/api/settings", json={"birthdate_bill": "1950-01-01"})

    data = client.get("/api/rmd").get_json()
    owners = {o["owner"]: o for o in data["owners"]}
    assert data["balance_source"] == "snapshot"
    assert data["balance_as_of"] == prior
    assert owners["Bill"]["balance"] == 265_000.0
    assert owners["Akiko"]["balance"] == 80_000.0
    bill = owners["Bill"]
    assert bill["rmd_amount"] == bill["projection"][0]["rmd_amount"]
    assert bill["rmd_amount"] > 0


def test_empty_snapshot_breakdown_is_a_real_zero(client, app, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=50_000)
    _insert_prior_snapshot(app, {})

    data = client.get("/api/rmd").get_json()
    owners = {o["owner"]: o for o in data["owners"]}
    assert data["balance_source"] == "snapshot"
    assert owners["Bill"]["balance"] == 0.0


def test_snapshot_without_breakdown_falls_back_to_today(client, app, insert_holding):
    insert_holding(owner="Bill", account_type="Rollover IRA", current_value=42_000)
    prior = _insert_prior_snapshot(app, None)

    data = client.get("/api/rmd").get_json()
    owners = {o["owner"]: o for o in data["owners"]}
    assert data["balance_source"] == "current"
    assert owners["Bill"]["balance"] == 42_000.0
    assert prior in data["balance_note"]
    assert "no owner and account breakdown" in data["balance_note"]


def test_withdrawal_floor_matches_the_rmd_for_that_calendar_year(client, app, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=100_000)
    prior = _insert_prior_snapshot(app, {"Bill": {"IRA": 1_000_000}})
    client.put("/api/settings", json={
        "birthdate_bill": "1940-06-01",
        "withdrawal_rate": 4,
        "withdrawal_return_rate": 6,
        "withdrawal_inflation_rate": 3,
        "withdrawal_years": 5,
        "tax_rate_ordinary": 22,
        "tax_rate_gains": 15,
    })

    rmd = client.get("/api/rmd").get_json()
    assert rmd["balance_source"] == "snapshot"
    assert rmd["balance_as_of"] == prior
    bill = next(o for o in rmd["owners"] if o["owner"] == "Bill")
    by_year = {row["calendar_year"]: row["rmd_amount"] for row in bill["projection"]}

    first = client.get("/api/withdrawal").get_json()["rows"][0]
    assert first["calendar_year"] == date.fromisoformat(today_iso()).year + 1
    assert first["rmd"] == by_year[first["calendar_year"]]
    assert first["rmd"] > first["planned_withdrawal"]
    assert first["withdrawal"] == first["rmd"]
    assert first["sources"]["pretax"] == first["withdrawal"]
    assert first["tax"] == round(first["sources"]["pretax"] * 22 / 100, 2)
    assert first["spendable"] == round(first["withdrawal"] - first["tax"], 2)


def test_not_yet_required_owner(client, insert_holding):
    insert_holding(owner="Akiko", account_type="403b", current_value=200_000)
    client.put("/api/settings", json={"birthdate_akiko": "2000-01-01"})

    r = client.get("/api/rmd")
    akiko = next(o for o in r.get_json()["owners"] if o["owner"] == "Akiko")
    assert akiko["required"] is False
    assert akiko["rmd_amount"] == 0.0
    assert akiko["years_until_required"] > 0

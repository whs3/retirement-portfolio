"""Cash-flow math and the manual cash-flow API."""

from portfolio.db import get_db
from portfolio.services.cash_flows import external_flow_from_share_change, period_return
from portfolio.timezone_util import today_iso


def test_share_increase_is_priced_at_the_new_value():
    # 10 shares at $150, then 15 shares marked at $160. The 5 new shares are
    # an $800 deposit. The $10 price increase on the original shares is not.
    assert external_flow_from_share_change(10, 1500, 15, 2400) == 800


def test_partial_sale_withdraws_proceeds_at_the_new_price():
    assert external_flow_from_share_change(10, 1500, 6, 960) == -640


def test_price_or_cost_basis_edit_is_not_a_cash_flow():
    assert external_flow_from_share_change(10, 1500, 10, 1800) == 0


def test_closing_a_position_withdraws_its_last_value():
    assert external_flow_from_share_change(10, 1500, 0, 0) == -1500


def test_period_return_without_flows_matches_value_change():
    stats = period_return(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [1000, 1100, 1200],
        [],
    )
    assert stats == {
        "value_change": 200.0,
        "net_flow": 0.0,
        "gain": 200.0,
        "gain_pct": 20.0,
    }


def test_add_holding_records_market_value_not_cost_basis(client, app):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Microsoft",
            "ticker": "MSFT",
            "asset_type": "stock",
            "owner": "Bill",
            "account_type": "IRA",
            "shares": 5,
            "cost_basis": 1000,
            "current_value": 1500,
        },
    )
    assert r.status_code == 201
    with app.app_context():
        rows = get_db().execute("SELECT * FROM cash_flows").fetchall()
    assert len(rows) == 1
    assert rows[0]["amount"] == 1500
    assert rows[0]["source"] == "holding_add"
    assert rows[0]["flow_date"] == today_iso()
    assert rows[0]["owner"] == "Bill"
    assert rows[0]["account_type"] == "IRA"


def test_same_day_sign_fix_then_delete_nets_to_zero(client, app):
    # Entered with the wrong sign, corrected without changing shares, then
    # removed. None of that is money entering or leaving the portfolio.
    r = client.post(
        "/api/holdings",
        json={
            "name": "Vanguard Target Retirement Income Fund",
            "ticker": "VTINX",
            "asset_type": "mutual_fund",
            "owner": "Bill",
            "account_type": "401k",
            "shares": -25000,
            "cost_basis": 342251.78,
            "current_value": 342251.78,
        },
    )
    hid = r.get_json()["id"]
    client.put(
        f"/api/holdings/{hid}",
        json={"cost_basis": -342251.78, "current_value": -342251.78},
    )
    with app.app_context():
        rows = get_db().execute("SELECT source, amount FROM cash_flows").fetchall()
    assert [(r["source"], r["amount"]) for r in rows] == [("holding_add", -342251.78)]

    client.delete(f"/api/holdings/{hid}")
    with app.app_context():
        net = get_db().execute("SELECT SUM(amount) AS s FROM cash_flows").fetchone()["s"]
    assert net == 0


def test_edit_on_a_later_day_keeps_the_original_add_flow(client, app):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Apple",
            "ticker": "AAPL",
            "asset_type": "stock",
            "shares": 10,
            "cost_basis": 1500,
            "current_value": 2000,
        },
    )
    hid = r.get_json()["id"]
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cash_flows SET flow_date = '2026-01-02'")
        db.commit()
    client.put(f"/api/holdings/{hid}", json={"current_value": 2500})
    with app.app_context():
        rows = get_db().execute("SELECT source, amount FROM cash_flows").fetchall()
    assert [(r["source"], r["amount"]) for r in rows] == [("holding_add", 2000)]


def test_cost_basis_edit_does_not_record_a_flow(client, seed_holdings, app):
    hid = seed_holdings["aapl"]
    r = client.put(f"/api/holdings/{hid}", json={"cost_basis": 1800, "current_value": 2100})
    assert r.status_code == 200
    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) AS c FROM cash_flows").fetchone()["c"]
    assert count == 0


def test_share_increase_records_the_new_shares(client, seed_holdings, app):
    hid = seed_holdings["aapl"]  # 10 shares, value 2000
    r = client.put(
        f"/api/holdings/{hid}",
        json={"shares": 15, "current_value": 3000, "cost_basis": 99999},
    )
    assert r.status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT * FROM cash_flows").fetchone()
    # New price is 3000/15 = 200. Five new shares are a $1,000 deposit,
    # not the cost-basis change.
    assert row["amount"] == 1000
    assert row["source"] == "holding_edit"


def test_delete_and_sell_all_record_withdrawals(client, seed_holdings, app):
    client.delete(f"/api/holdings/{seed_holdings['voo']}")
    client.post(
        "/api/holdings/sell-all",
        json={"ticker": "AAPL", "owner": "Bill", "account_type": "IRA"},
    )
    with app.app_context():
        rows = get_db().execute(
            "SELECT source, amount FROM cash_flows ORDER BY id"
        ).fetchall()
    assert [(r["source"], r["amount"]) for r in rows] == [
        ("holding_delete", -2500),
        ("sell_all", -2000),
    ]


def test_manual_cash_flow_create_and_delete(client, app):
    created = client.post(
        "/api/cash-flows",
        json={
            "flow_date": "2026-01-15",
            "amount": -500,
            "owner": "Akiko",
            "account_type": "Broker",
            "ticker": "vti",
            "note": "Spent dividends",
        },
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["amount"] == -500
    assert body["ticker"] == "VTI"
    assert body["source"] == "manual"
    assert body["owner"] == "Akiko"

    deleted = client.delete(f"/api/cash-flows/{body['id']}")
    assert deleted.status_code == 200
    missing = client.delete(f"/api/cash-flows/{body['id']}")
    assert missing.status_code == 404
    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) AS c FROM cash_flows").fetchone()["c"]
    assert count == 0


def test_manual_cash_flow_rejects_bad_input(client):
    future = client.post(
        "/api/cash-flows",
        json={"flow_date": "2999-01-01", "amount": 10},
    )
    assert future.status_code == 400
    zero = client.post(
        "/api/cash-flows",
        json={"flow_date": "2026-01-01", "amount": 0},
    )
    assert zero.status_code == 400
    ticker = client.post(
        "/api/cash-flows",
        json={"flow_date": "2026-01-01", "amount": 10, "ticker": "BAD TICKER!"},
    )
    assert ticker.status_code == 400

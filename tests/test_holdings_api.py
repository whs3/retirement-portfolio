"""API tests for holdings CRUD and sell-all."""

from portfolio.db import get_db


def test_list_holdings_empty(client):
    r = client.get("/api/holdings")
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_holdings_seeded(client, seed_holdings):
    r = client.get("/api/holdings")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 4
    tickers = {h["ticker"] for h in data}
    assert "AAPL" in tickers
    assert "VOO" in tickers


def test_add_holding(client):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Microsoft",
            "ticker": "msft",
            "asset_type": "stock",
            "category": "Technology",
            "owner": "Bill",
            "account_type": "IRA",
            "shares": 5,
            "cost_basis": 1000,
            "current_value": 1500,
            "purchase_date": "2023-06-01",
        },
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["success"] is True
    assert body["id"] > 0

    listed = client.get("/api/holdings").get_json()
    msft = next(h for h in listed if h["ticker"] == "MSFT")
    assert msft["name"] == "Microsoft"
    assert msft["shares"] == 5


def test_add_holding_missing_fields(client):
    r = client.post("/api/holdings", json={"name": "X"})
    assert r.status_code == 400
    assert "Missing required fields" in r.get_json()["error"]


def test_add_holding_invalid_number(client):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Bad",
            "asset_type": "stock",
            "cost_basis": "not-a-number",
            "current_value": 100,
        },
    )
    assert r.status_code == 400
    assert "must be a number" in r.get_json()["error"]


def test_add_cash_special_ticker(client):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Cash",
            "ticker": "$$CASH",
            "asset_type": "cash",
            "shares": 250.5,
            "cost_basis": 250.5,
            "current_value": 999,  # should be overwritten to shares
        },
    )
    assert r.status_code == 201
    h = client.get("/api/holdings").get_json()[0]
    assert h["category"] == "Cash"
    assert h["current_value"] == 250.5


def test_update_holding(client, seed_holdings):
    hid = seed_holdings["aapl"]
    r = client.put(
        f"/api/holdings/{hid}",
        json={"shares": 12, "current_value": 2400, "notes": "topped up"},
    )
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    h = next(x for x in client.get("/api/holdings").get_json() if x["id"] == hid)
    assert h["shares"] == 12
    assert h["current_value"] == 2400
    assert h["notes"] == "topped up"


def test_update_holding_not_found(client):
    r = client.put("/api/holdings/99999", json={"shares": 1})
    assert r.status_code == 404


def test_delete_holding(client, seed_holdings):
    hid = seed_holdings["bond"]
    r = client.delete(f"/api/holdings/{hid}")
    assert r.status_code == 200
    ids = {h["id"] for h in client.get("/api/holdings").get_json()}
    assert hid not in ids


def test_delete_holding_not_found(client):
    r = client.delete("/api/holdings/99999")
    assert r.status_code == 404


def test_sell_all_nets_to_zero(client, seed_holdings, app):
    """Sell-all inserts an offsetting row so net shares/value become ~0."""
    r = client.post(
        "/api/holdings/sell-all",
        json={"ticker": "AAPL", "owner": "Bill", "account_type": "IRA"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["success"] is True
    assert body["shares_sold"] == 10
    assert body["value_sold"] == 2000

    with app.app_context():
        rows = get_db().execute(
            "SELECT * FROM holdings WHERE ticker=? AND owner=? AND account_type=?",
            ("AAPL", "Bill", "IRA"),
        ).fetchall()
        assert abs(sum(r["shares"] for r in rows)) < 1e-9
        assert abs(sum(r["current_value"] for r in rows)) < 0.01


def test_sell_all_requires_ticker(client):
    r = client.post("/api/holdings/sell-all", json={"owner": "Bill"})
    assert r.status_code == 400
    assert "Ticker is required" in r.get_json()["error"]


def test_sell_all_invalid_ticker(client):
    r = client.post(
        "/api/holdings/sell-all",
        json={"ticker": "BAD TICKER!", "owner": "Bill", "account_type": "IRA"},
    )
    assert r.status_code == 400
    assert "Invalid ticker" in r.get_json()["error"]


def test_sell_all_not_found(client):
    r = client.post(
        "/api/holdings/sell-all",
        json={"ticker": "ZZZZ", "owner": "Nobody", "account_type": "IRA"},
    )
    assert r.status_code == 404


def test_sell_all_already_sold(client, seed_holdings):
    client.post(
        "/api/holdings/sell-all",
        json={"ticker": "AAPL", "owner": "Bill", "account_type": "IRA"},
    )
    r = client.post(
        "/api/holdings/sell-all",
        json={"ticker": "AAPL", "owner": "Bill", "account_type": "IRA"},
    )
    assert r.status_code == 400
    assert "already fully sold" in r.get_json()["error"]


def test_add_holding_allows_negative_sell_transaction(client):
    r = client.post(
        "/api/holdings",
        json={
            "name": "Apple Inc.",
            "ticker": "AAPL",
            "asset_type": "stock",
            "shares": -2,
            "cost_basis": -300,
            "current_value": -400,
        },
    )
    assert r.status_code == 201
    h = client.get("/api/holdings").get_json()[0]
    assert h["shares"] == -2

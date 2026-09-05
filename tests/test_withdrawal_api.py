"""API tests for GET /api/withdrawal."""


def test_defaults_used_when_no_query_params(client):
    r = client.get("/api/withdrawal")
    assert r.status_code == 200
    data = r.get_json()
    assert data["assumptions"]["annual_rate_pct"] == 4.0
    assert data["assumptions"]["expected_return_pct"] == 6.0
    assert data["assumptions"]["inflation_pct"] == 3.0
    assert data["assumptions"]["years"] == 30
    assert data["starting_balance"] == 0.0


def test_starting_balance_matches_holdings_total(client, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=100_000)
    insert_holding(owner="Akiko", account_type="Roth IRA", current_value=50_000)

    r = client.get("/api/withdrawal")
    assert r.get_json()["starting_balance"] == 150_000.0


def test_query_params_override_defaults(client, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=200_000)
    r = client.get("/api/withdrawal?rate=5&return_rate=7&inflation_rate=2&years=10")
    data = r.get_json()
    assert data["assumptions"] == {
        "annual_rate_pct": 5.0,
        "expected_return_pct": 7.0,
        "inflation_pct": 2.0,
        "years": 10,
    }
    assert len(data["rows"]) == 10


def test_persisted_assumptions_used_as_defaults(client, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=100_000)
    client.put("/api/settings", json={"withdrawal_rate": 3.5, "withdrawal_years": 20})

    r = client.get("/api/withdrawal")
    data = r.get_json()
    assert data["assumptions"]["annual_rate_pct"] == 3.5
    assert data["assumptions"]["years"] == 20


def test_invalid_rate_rejected(client):
    r = client.get("/api/withdrawal?rate=abc")
    assert r.status_code == 400


def test_invalid_years_rejected(client):
    r = client.get("/api/withdrawal?years=0")
    assert r.status_code == 400

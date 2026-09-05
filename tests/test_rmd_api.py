"""API tests for GET /api/rmd."""


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
    owners = {o["owner"]: o for o in r.get_json()["owners"]}
    assert owners["Bill"]["balance"] == 150_000.0
    assert owners["Akiko"]["balance"] == 0.0


def test_with_birthdate_includes_rmd_fields(client, insert_holding):
    insert_holding(owner="Bill", account_type="IRA", current_value=500_000)
    client.put("/api/settings", json={"birthdate_bill": "1950-01-01"})

    r = client.get("/api/rmd")
    bill = next(o for o in r.get_json()["owners"] if o["owner"] == "Bill")
    assert bill["birthdate"] == "1950-01-01"
    assert bill["required"] is True
    assert bill["rmd_amount"] > 0


def test_not_yet_required_owner(client, insert_holding):
    insert_holding(owner="Akiko", account_type="403b", current_value=200_000)
    client.put("/api/settings", json={"birthdate_akiko": "2000-01-01"})

    r = client.get("/api/rmd")
    akiko = next(o for o in r.get_json()["owners"] if o["owner"] == "Akiko")
    assert akiko["required"] is False
    assert akiko["rmd_amount"] == 0.0
    assert akiko["years_until_required"] > 0

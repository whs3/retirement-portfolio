"""API tests for the audit log."""


def test_audit_empty(client):
    r = client.get("/api/audit")
    assert r.status_code == 200
    assert r.get_json() == []


def test_audit_records_add_edit_delete(client):
    # ADD
    r = client.post(
        "/api/holdings",
        json={
            "name": "Nvidia",
            "ticker": "NVDA",
            "asset_type": "stock",
            "cost_basis": 500,
            "current_value": 800,
            "shares": 2,
        },
    )
    hid = r.get_json()["id"]

    # EDIT
    client.put(f"/api/holdings/{hid}", json={"current_value": 900})

    # DELETE
    client.delete(f"/api/holdings/{hid}")

    entries = client.get("/api/audit").get_json()
    actions = [e["action"] for e in entries]
    # Newest first
    assert "DELETE" in actions
    assert "EDIT" in actions
    assert "ADD" in actions

    add = next(e for e in entries if e["action"] == "ADD")
    assert add["ticker"] == "NVDA"
    assert add["name"] == "Nvidia"
    assert "timestamp" in add

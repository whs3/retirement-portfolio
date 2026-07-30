"""API tests for settings (including FMP key masking)."""


def test_get_settings_empty(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.get_json() == {}


def test_put_and_mask_fmp_key(client):
    r = client.put("/api/settings", json={"fmp_api_key": "secret-key-123"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    got = client.get("/api/settings").get_json()
    assert got.get("fmp_api_key_set") is True
    assert "fmp_api_key" not in got  # raw key must not leak


def test_put_unknown_setting_rejected(client):
    r = client.put("/api/settings", json={"not_allowed": "x"})
    assert r.status_code == 400
    assert "Unknown setting" in r.get_json()["error"]


def test_put_non_string_rejected(client):
    r = client.put("/api/settings", json={"fmp_api_key": 12345})
    assert r.status_code == 400
    assert "Invalid value" in r.get_json()["error"]


def test_clear_fmp_key(client):
    client.put("/api/settings", json={"fmp_api_key": "abc"})
    client.put("/api/settings", json={"fmp_api_key": ""})
    got = client.get("/api/settings").get_json()
    assert got.get("fmp_api_key_set") is False

"""API tests for settings (including FMP key masking)."""

import pytest

from portfolio.services.settings import (
    DEFAULT_PRICE_REFRESH_MINUTES,
    parse_price_refresh_minutes,
)


def test_get_settings_empty(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.get_json() == {
        "price_refresh_minutes": str(DEFAULT_PRICE_REFRESH_MINUTES),
    }


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


@pytest.mark.parametrize(
    "raw, expected",
    [
        (0, 0),
        (15, 15),
        ("15", 15),
        (" 0 ", 0),
        (1440, 1440),
        (15.0, 15),
    ],
)
def test_parse_price_refresh_minutes_valid(raw, expected):
    assert parse_price_refresh_minutes(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, True, False, "", "abc", -1, 1441, 1.5, "1.5", "nan", "inf"],
)
def test_parse_price_refresh_minutes_invalid(raw):
    with pytest.raises(ValueError):
        parse_price_refresh_minutes(raw)


def test_put_price_refresh_minutes(client):
    r = client.put("/api/settings", json={"price_refresh_minutes": 30})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got["price_refresh_minutes"] == "30"

    r = client.put("/api/settings", json={"price_refresh_minutes": "0"})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got["price_refresh_minutes"] == "0"


def test_put_price_refresh_minutes_rejected(client):
    r = client.put("/api/settings", json={"price_refresh_minutes": -5})
    assert r.status_code == 400
    assert "negative" in r.get_json()["error"]

    r = client.put("/api/settings", json={"price_refresh_minutes": 2000})
    assert r.status_code == 400
    assert "exceed" in r.get_json()["error"]


def test_put_and_get_birthdate(client):
    r = client.put("/api/settings", json={"birthdate_bill": "1960-05-15"})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got["birthdate_bill"] == "1960-05-15"


def test_put_birthdate_clears_with_empty_string(client):
    client.put("/api/settings", json={"birthdate_bill": "1960-05-15"})
    r = client.put("/api/settings", json={"birthdate_bill": ""})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got["birthdate_bill"] == ""


@pytest.mark.parametrize(
    "raw",
    ["not-a-date", "2026-13-40", "05/15/1960", "2099-01-01", "1899-01-01", 12345],
)
def test_put_birthdate_rejected(client, raw):
    r = client.put("/api/settings", json={"birthdate_bill": raw})
    assert r.status_code == 400


@pytest.mark.parametrize("key", ["withdrawal_rate", "withdrawal_return_rate", "withdrawal_inflation_rate"])
def test_put_withdrawal_rate_valid(client, key):
    r = client.put("/api/settings", json={key: 4.5})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got[key] == "4.5"


@pytest.mark.parametrize("key", ["withdrawal_rate", "withdrawal_return_rate", "withdrawal_inflation_rate"])
@pytest.mark.parametrize("raw", [-1, 51, "abc", float("nan")])
def test_put_withdrawal_rate_rejected(client, key, raw):
    r = client.put("/api/settings", json={key: raw})
    assert r.status_code == 400


def test_put_withdrawal_years_valid(client):
    r = client.put("/api/settings", json={"withdrawal_years": 30})
    assert r.status_code == 200
    got = client.get("/api/settings").get_json()
    assert got["withdrawal_years"] == "30"


@pytest.mark.parametrize("raw", [0, -5, 61, 30.5, "abc"])
def test_put_withdrawal_years_rejected(client, raw):
    r = client.put("/api/settings", json={"withdrawal_years": raw})
    assert r.status_code == 400


def test_scheduler_not_started_in_testing(app):
    assert app.extensions.get("price_refresh_thread") is None


def test_scheduler_starts_outside_testing(monkeypatch):
    from types import SimpleNamespace

    from portfolio.services.price_scheduler import start_price_refresh_scheduler

    started = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            started.append(self)

        def start(self):
            pass

    monkeypatch.setattr(
        "portfolio.services.price_scheduler.threading.Thread", FakeThread
    )
    app = SimpleNamespace(
        config={"TESTING": False},
        debug=False,
        extensions={},
    )
    start_price_refresh_scheduler(app)
    assert len(started) == 1
    assert app.extensions["price_refresh_thread"] is started[0]

    start_price_refresh_scheduler(app)
    assert len(started) == 1  # idempotent

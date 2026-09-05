"""Security hook tests: LAN allowlist, CSRF, and response headers."""

import pytest

from portfolio import create_app


def test_local_request_allowed(client):
    r = client.get("/api/holdings")
    assert r.status_code == 200


def test_remote_request_forbidden(client):
    r = client.get("/api/holdings", environ_base={"REMOTE_ADDR": "8.8.8.8"})
    assert r.status_code == 403


def test_lan_192_allowed(client):
    r = client.get("/api/holdings", environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert r.status_code == 200


def test_security_headers_present(client):
    r = client.get("/api/holdings")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-XSS-Protection"] == "1; mode=block"


def test_pages_render(client):
    for path in (
        "/",
        "/holdings",
        "/performance",
        "/lookup",
        "/overlap",
        "/rebalance",
        "/insights",
        "/audit",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert b"RetireTrack" in r.data or b"html" in r.data.lower()


@pytest.fixture
def csrf_client(tmp_path):
    """Client with CSRF checks enabled (the default test app turns them off)."""
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-not-for-production",
        "WTF_CSRF_ENABLED": True,
        "WTF_CSRF_TIME_LIMIT": None,
        "RATELIMIT_ENABLED": False,
        "PRICE_REFRESH_SCHEDULER": False,
        "DATABASE": str(tmp_path / "csrf.db"),
        "AUDIT_LOG": str(tmp_path / "csrf_audit.log"),
        "TEMPLATES_AUTO_RELOAD": False,
    })
    return app.test_client()


def test_csrf_time_limit_disabled():
    from portfolio.config import Config
    assert Config.WTF_CSRF_TIME_LIMIT is None


def test_refresh_without_csrf_returns_json(csrf_client):
    r = csrf_client.post("/api/holdings/refresh-prices")
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None
    assert data["code"] == "csrf"
    assert "error" in data


def test_csrf_token_endpoint_and_refresh(csrf_client):
    tok = csrf_client.get("/api/csrf-token")
    assert tok.status_code == 200
    token = tok.get_json()["csrf_token"]
    assert token

    r = csrf_client.post(
        "/api/holdings/refresh-prices",
        headers={"X-CSRFToken": token},
    )
    # yfinance is not called in a meaningful way here; we only care CSRF passed.
    # Without holdings the endpoint still returns 200 with empty lists.
    assert r.status_code == 200
    body = r.get_json()
    assert "updated" in body
    assert "skipped" in body
    assert "errors" in body

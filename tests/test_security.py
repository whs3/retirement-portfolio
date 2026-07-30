"""Security hook tests: LAN allowlist and response headers."""


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

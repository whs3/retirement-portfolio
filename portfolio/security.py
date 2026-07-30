"""Request security hooks: network allowlist and response headers."""

from flask import abort, request


def local_network_only():
    addr = request.remote_addr or ""
    if addr not in ("127.0.0.1", "::1") and not addr.startswith("192.168."):
        abort(403)


def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

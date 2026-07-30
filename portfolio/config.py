"""Application configuration loaded from environment variables."""

import os
import secrets


class Config:
    """Default configuration for the retirement portfolio app."""

    DATABASE = os.getenv("PORTFOLIO_DATABASE", "portfolio.db")
    AUDIT_LOG = os.getenv("PORTFOLIO_AUDIT_LOG", "portfolio_audit.log")
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    WTF_CSRF_HEADERS = ["X-CSRFToken"]
    TEMPLATES_AUTO_RELOAD = True
    TESTING = False
    # flask-limiter: set False in tests to avoid rate-limit noise
    RATELIMIT_ENABLED = True


class TestConfig(Config):
    """In-memory / temp-file friendly config for pytest."""

    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    TEMPLATES_AUTO_RELOAD = False

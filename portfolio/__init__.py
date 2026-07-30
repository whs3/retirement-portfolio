"""Retirement portfolio Flask application factory."""

from pathlib import Path

from flask import Flask, jsonify

from portfolio.config import Config
from portfolio.db import close_db, init_db
from portfolio.extensions import csrf, limiter
from portfolio.routes import register_blueprints
from portfolio.security import local_network_only, security_headers
from portfolio.services.audit import init_audit_log
from portfolio.timezone_util import SERVER_TIMEZONE

# Project root (parent of the portfolio package) — templates/ and static/ live here
_ROOT = Path(__file__).resolve().parent.parent


def create_app(config_object=Config):
    """Create and configure the Flask application.

    ``config_object`` may be a config class, an instance, or a dict of overrides.
    """
    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    if isinstance(config_object, dict):
        app.config.from_object(Config)
        app.config.from_mapping(config_object)
    else:
        app.config.from_object(config_object)

    # Extensions
    csrf.init_app(app)
    limiter.init_app(app)

    # Database
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    # Audit file handler
    init_audit_log(app.config["AUDIT_LOG"])

    # Security hooks
    app.before_request(local_network_only)
    app.after_request(security_headers)

    @app.context_processor
    def inject_server_timezone():
        return {"server_timezone": SERVER_TIMEZONE}

    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Return JSON error for API clients instead of HTML."""
        return jsonify({
            "error": "Rate limit exceeded. Please wait a moment before trying again."
        }), 429

    register_blueprints(app)
    return app

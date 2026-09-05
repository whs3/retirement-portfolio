"""Register all Flask blueprints."""

from portfolio.routes.audit import bp as audit_bp
from portfolio.routes.export import bp as export_bp
from portfolio.routes.holdings import bp as holdings_bp
from portfolio.routes.insights import bp as insights_bp
from portfolio.routes.lookup import bp as lookup_bp
from portfolio.routes.overlap import bp as overlap_bp
from portfolio.routes.pages import bp as pages_bp
from portfolio.routes.performance import bp as performance_bp
from portfolio.routes.portfolio import bp as portfolio_bp
from portfolio.routes.prices import bp as prices_bp
from portfolio.routes.rmd import bp as rmd_bp
from portfolio.routes.settings import bp as settings_bp
from portfolio.routes.withdrawal import bp as withdrawal_bp


def register_blueprints(app):
    app.register_blueprint(pages_bp)
    app.register_blueprint(holdings_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(prices_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(overlap_bp)
    app.register_blueprint(performance_bp)
    app.register_blueprint(lookup_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(rmd_bp)
    app.register_blueprint(withdrawal_bp)

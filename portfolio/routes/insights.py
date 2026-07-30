"""Market insights API."""

from flask import Blueprint, jsonify

from portfolio.extensions import limiter
from portfolio.services.insights import build_insights

bp = Blueprint("insights_api", __name__)


@bp.route("/api/insights")
@limiter.limit("6 per hour")
def get_insights():
    """
    Analyze current holdings using analyst consensus and price targets (yfinance).
    Returns market snapshot + per-ticker analyst view + aggregated recommendations.
    """
    return jsonify(build_insights())

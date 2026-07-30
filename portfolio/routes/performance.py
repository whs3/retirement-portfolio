"""Portfolio performance history API."""

from flask import Blueprint, jsonify

from portfolio.extensions import limiter
from portfolio.services.performance import build_performance

bp = Blueprint("performance_api", __name__)


@bp.route("/api/performance")
@limiter.limit("10 per hour")
def get_performance():
    return jsonify(build_performance())

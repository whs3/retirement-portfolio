"""Portfolio performance history API."""

from flask import Blueprint, jsonify

from portfolio.extensions import limiter
from portfolio.services.snapshots import (
    backfill_once,
    capture_snapshot,
    get_performance_history,
)

bp = Blueprint("performance_api", __name__)


@bp.route("/api/performance")
@limiter.limit("10 per hour")
def get_performance():
    backfill_once()
    capture_snapshot()
    return jsonify(get_performance_history())

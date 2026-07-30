"""Stock overlap analysis API."""

from flask import Blueprint, jsonify

from portfolio.extensions import limiter
from portfolio.services.overlap import build_overlap

bp = Blueprint("overlap_api", __name__)


@bp.route("/api/overlap")
@limiter.limit("10 per hour")
def get_overlap():
    return jsonify(build_overlap())

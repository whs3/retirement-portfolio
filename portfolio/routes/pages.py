"""HTML page routes."""

from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@bp.route("/holdings")
def holdings_page():
    return render_template("holdings.html")


@bp.route("/rebalance")
def rebalance_page():
    return render_template("rebalance.html")


@bp.route("/insights")
def insights_page():
    return render_template("insights.html")


@bp.route("/audit")
def audit_page():
    return render_template("audit.html")


@bp.route("/overlap")
def overlap_page():
    return render_template("overlap.html")


@bp.route("/performance")
def performance_page():
    return render_template("performance.html")


@bp.route("/lookup")
def lookup_page():
    return render_template("lookup.html")


@bp.route("/planning")
def planning_page():
    return render_template("planning.html")

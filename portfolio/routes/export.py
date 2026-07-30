"""CSV export API."""

import csv
import io
from datetime import datetime

from flask import Blueprint, send_file

from portfolio.db import get_db

bp = Blueprint("export", __name__)


@bp.route("/api/export/csv")
def export_csv():
    holdings = get_db().execute(
        "SELECT * FROM holdings ORDER BY asset_type, name"
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Ticker", "Asset Type", "Owner", "Account Type", "Shares",
        "Cost Basis ($)", "Current Value ($)",
        "Gain/Loss ($)", "Gain/Loss (%)",
        "Purchase Date", "Notes",
    ])
    for h in holdings:
        gain = h["current_value"] - h["cost_basis"]
        gain_pct = (gain / h["cost_basis"] * 100) if h["cost_basis"] else 0
        writer.writerow([
            h["name"],
            h["ticker"],
            h["asset_type"].replace("_", " ").title(),
            h["owner"] or "",
            h["account_type"] or "",
            h["shares"],
            f"{h['cost_basis']:.2f}",
            f"{h['current_value']:.2f}",
            f"{gain:.2f}",
            f"{gain_pct:.2f}",
            h["purchase_date"],
            h["notes"],
        ])

    filename = f"portfolio_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )

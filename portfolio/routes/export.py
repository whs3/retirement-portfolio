"""CSV export/import API."""

import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from portfolio.db import get_db
from portfolio.services.audit import audit
from portfolio.validators import VALID_TICKER, parse_float

bp = Blueprint("export", __name__)

# Shared with import so a round-tripped file (export -> edit -> re-import) is
# always recognized.
CSV_HEADERS = [
    "Name", "Ticker", "Asset Type", "Owner", "Account Type", "Shares",
    "Cost Basis ($)", "Current Value ($)",
    "Gain/Loss ($)", "Gain/Loss (%)",
    "Purchase Date", "Notes",
]

ALLOWED_ASSET_TYPES = {"stock", "bond", "etf", "mutual_fund", "cash"}


@bp.route("/api/export/csv")
def export_csv():
    holdings = get_db().execute(
        "SELECT * FROM holdings ORDER BY asset_type, name"
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)
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


def _parse_import_row(row: dict, row_num: int) -> dict:
    name = (row.get("Name") or "").strip()
    if not name:
        raise ValueError("Name is required")

    ticker = (row.get("Ticker") or "").strip().upper()
    if ticker and ticker != "$$CASH" and not VALID_TICKER.match(ticker):
        raise ValueError("Invalid ticker format")

    asset_type_raw = (row.get("Asset Type") or "").strip()
    asset_type = asset_type_raw.lower().replace(" ", "_")
    if asset_type not in ALLOWED_ASSET_TYPES:
        raise ValueError(f"Invalid asset type: '{asset_type_raw}'")

    shares = parse_float(row.get("Shares") or 0, "Shares")
    cost_basis = parse_float(row.get("Cost Basis ($)") or 0, "Cost Basis")
    current_value = parse_float(row.get("Current Value ($)") or 0, "Current Value")

    category = ""
    if ticker == "$$CASH":
        category = "Cash"
        current_value = shares

    return {
        "name": name,
        "ticker": ticker,
        "asset_type": asset_type,
        "category": category,
        "owner": (row.get("Owner") or "").strip(),
        "account_type": (row.get("Account Type") or "").strip(),
        "shares": shares,
        "cost_basis": cost_basis,
        "current_value": current_value,
        "purchase_date": (row.get("Purchase Date") or "").strip(),
        "notes": (row.get("Notes") or "").strip(),
    }


@bp.route("/api/import/csv", methods=["POST"])
def import_csv():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        text = upload.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 encoded CSV"}), 400

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {(f or "").strip() for f in (reader.fieldnames or [])}
    if fieldnames != set(CSV_HEADERS):
        return jsonify({
            "error": "CSV headers do not match the expected export format. "
                     "Use File > Export CSV as a starting template."
        }), 400

    parsed_rows = []
    row_errors = []
    for row_num, row in enumerate(reader, start=2):
        try:
            parsed_rows.append(_parse_import_row(row, row_num))
        except ValueError as exc:
            row_errors.append({"row": row_num, "error": str(exc)})

    if row_errors:
        return jsonify({
            "error": "CSV contains invalid rows; nothing was imported",
            "row_errors": row_errors,
        }), 400

    if not parsed_rows:
        return jsonify({"error": "No data rows found in CSV"}), 400

    db = get_db()
    now = datetime.utcnow().isoformat()
    for r in parsed_rows:
        db.execute(
            """INSERT INTO holdings
                   (name, ticker, asset_type, category, owner, account_type, shares,
                    cost_basis, current_value, purchase_date, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["name"], r["ticker"], r["asset_type"], r["category"], r["owner"],
                r["account_type"], r["shares"], r["cost_basis"], r["current_value"],
                r["purchase_date"], r["notes"], now, now,
            ),
        )
        audit(
            "IMPORT", r["ticker"], r["name"],
            current_value=r["current_value"], cost_basis=r["cost_basis"],
        )
    db.commit()

    return jsonify({"success": True, "imported": len(parsed_rows)}), 201

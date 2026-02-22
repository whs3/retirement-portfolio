import csv
import io
import logging
import sqlite3
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request, send_file

app = Flask(__name__)
app.config["DATABASE"] = "portfolio.db"
app.config["AUDIT_LOG"] = "portfolio_audit.log"

# ── Audit logger ──────────────────────────────────────────────────────────────

_audit_logger = logging.getLogger("portfolio.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False  # don't bleed into Flask's root logger

_audit_handler = logging.FileHandler(app.config["AUDIT_LOG"])
_audit_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
_audit_logger.addHandler(_audit_handler)


def audit(action: str, ticker: str, name: str, **fields):
    """Write one line to the audit log.

    Example output:
        2026-02-21 14:30:00 | ADD    | AAPL | Apple Inc. | current_value=$11200.00 cost_basis=$7500.00
    """
    ticker_col = (ticker or "—").ljust(6)
    kv = "  ".join(
        f"{k}=${v:.2f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in fields.items()
    )
    _audit_logger.info("%-6s | %s | %s | %s", action, ticker_col, name, kv)


# ── Database helpers ──────────────────────────────────────────────────────────


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            ticker        TEXT    NOT NULL DEFAULT '',
            asset_type    TEXT    NOT NULL,
            shares        REAL    NOT NULL DEFAULT 0,
            cost_basis    REAL    NOT NULL DEFAULT 0,
            current_value REAL    NOT NULL DEFAULT 0,
            purchase_date TEXT    NOT NULL DEFAULT '',
            notes         TEXT    NOT NULL DEFAULT '',
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS target_allocations (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type         TEXT    NOT NULL UNIQUE,
            target_percentage  REAL    NOT NULL DEFAULT 0
        );

        INSERT OR IGNORE INTO target_allocations (asset_type, target_percentage) VALUES
            ('stock',       60),
            ('bond',        30),
            ('etf',          5),
            ('mutual_fund',  5);
        """
    )
    conn.commit()
    conn.close()


# Initialise on startup (works with both `python app.py` and `flask run`)
with app.app_context():
    init_db()


# ── Page routes ───────────────────────────────────────────────────────────────


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/holdings")
def holdings_page():
    return render_template("holdings.html")


@app.route("/rebalance")
def rebalance_page():
    return render_template("rebalance.html")


@app.route("/audit")
def audit_page():
    return render_template("audit.html")


# ── API: Audit log ───────────────────────────────────────────────────────────


@app.route("/api/audit")
def get_audit_log():
    log_path = app.config["AUDIT_LOG"]
    entries = []
    try:
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Format: "2026-02-21 22:22:49 | ADD    | NVDA   | Nvidia Corp. | k=$v  k=$v"
                parts = [p.strip() for p in line.split("|", 4)]
                if len(parts) < 4:
                    continue
                timestamp, action, ticker, name = parts[0], parts[1], parts[2], parts[3]
                raw_fields = parts[4] if len(parts) == 5 else ""

                fields = {}
                for token in raw_fields.split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        fields[k] = v

                entries.append({
                    "timestamp": timestamp,
                    "action":    action.strip(),
                    "ticker":    ticker.strip(),
                    "name":      name.strip(),
                    "fields":    fields,
                })
    except FileNotFoundError:
        pass

    entries.reverse()  # newest first
    return jsonify(entries)


# ── API: Holdings ─────────────────────────────────────────────────────────────


@app.route("/api/holdings", methods=["GET"])
def get_holdings():
    rows = get_db().execute(
        "SELECT * FROM holdings ORDER BY asset_type, name"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/holdings", methods=["POST"])
def add_holding():
    data = request.get_json()
    missing = [f for f in ("name", "asset_type", "cost_basis", "current_value")
               if not data.get(f) and data.get(f) != 0]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    now = datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, shares, cost_basis, current_value,
                purchase_date, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            (data.get("ticker") or "").strip().upper(),
            data["asset_type"],
            float(data.get("shares") or 0),
            float(data["cost_basis"]),
            float(data["current_value"]),
            data.get("purchase_date") or "",
            (data.get("notes") or "").strip(),
            now,
            now,
        ),
    )
    db.commit()
    audit(
        "ADD",
        (data.get("ticker") or "").strip().upper(),
        data["name"].strip(),
        current_value=float(data["current_value"]),
        cost_basis=float(data["cost_basis"]),
    )
    return jsonify({"id": cur.lastrowid, "success": True}), 201


@app.route("/api/holdings/<int:hid>", methods=["PUT"])
def update_holding(hid):
    data = request.get_json()
    db = get_db()
    row = db.execute("SELECT * FROM holdings WHERE id = ?", (hid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    now = datetime.utcnow().isoformat()
    db.execute(
        """UPDATE holdings
           SET name=?, ticker=?, asset_type=?, shares=?, cost_basis=?,
               current_value=?, purchase_date=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            (data.get("name") or row["name"]).strip(),
            (data.get("ticker") or row["ticker"]).strip().upper(),
            data.get("asset_type") or row["asset_type"],
            float(data.get("shares") if data.get("shares") is not None else row["shares"]),
            float(data.get("cost_basis") if data.get("cost_basis") is not None else row["cost_basis"]),
            float(data.get("current_value") if data.get("current_value") is not None else row["current_value"]),
            data.get("purchase_date") or row["purchase_date"],
            (data.get("notes") or row["notes"]).strip(),
            now,
            hid,
        ),
    )
    db.commit()
    new_value = float(data.get("current_value") if data.get("current_value") is not None else row["current_value"])
    new_cost  = float(data.get("cost_basis")    if data.get("cost_basis")    is not None else row["cost_basis"])
    audit(
        "EDIT",
        (data.get("ticker") or row["ticker"]).strip().upper(),
        (data.get("name") or row["name"]).strip(),
        value_change=new_value - row["current_value"],
        cost_basis_change=new_cost - row["cost_basis"],
        current_value=new_value,
        cost_basis=new_cost,
    )
    return jsonify({"success": True})


@app.route("/api/holdings/<int:hid>", methods=["DELETE"])
def delete_holding(hid):
    db = get_db()
    row = db.execute("SELECT * FROM holdings WHERE id = ?", (hid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM holdings WHERE id = ?", (hid,))
    db.commit()
    audit(
        "DELETE",
        row["ticker"],
        row["name"],
        current_value=row["current_value"],
        cost_basis=row["cost_basis"],
    )
    return jsonify({"success": True})


# ── API: Portfolio summary ────────────────────────────────────────────────────


@app.route("/api/portfolio/summary")
def portfolio_summary():
    holdings = get_db().execute("SELECT * FROM holdings").fetchall()
    total_value = sum(h["current_value"] for h in holdings)
    total_cost = sum(h["cost_basis"] for h in holdings)
    gain_loss = total_value - total_cost
    gain_loss_pct = (gain_loss / total_cost * 100) if total_cost else 0

    by_type: dict[str, float] = {}
    for h in holdings:
        by_type.setdefault(h["asset_type"], 0)
        by_type[h["asset_type"]] += h["current_value"]

    allocation = [
        {
            "asset_type": t,
            "value": v,
            "percentage": (v / total_value * 100) if total_value else 0,
        }
        for t, v in sorted(by_type.items())
    ]

    return jsonify(
        {
            "total_value": total_value,
            "total_cost": total_cost,
            "gain_loss": gain_loss,
            "gain_loss_pct": gain_loss_pct,
            "count": len(holdings),
            "allocation": allocation,
        }
    )


# ── API: Target allocations ───────────────────────────────────────────────────


@app.route("/api/allocations", methods=["GET"])
def get_allocations():
    rows = get_db().execute(
        "SELECT * FROM target_allocations ORDER BY asset_type"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/allocations", methods=["PUT"])
def update_allocations():
    data = request.get_json()  # [{asset_type, target_percentage}, ...]
    total = sum(float(item["target_percentage"]) for item in data)
    if abs(total - 100) > 0.01:
        return jsonify({"error": f"Allocations must sum to 100% (currently {total:.1f}%)"}), 400

    db = get_db()
    for item in data:
        db.execute(
            """INSERT INTO target_allocations (asset_type, target_percentage)
               VALUES (?, ?)
               ON CONFLICT(asset_type) DO UPDATE SET target_percentage = excluded.target_percentage""",
            (item["asset_type"], float(item["target_percentage"])),
        )
    db.commit()
    return jsonify({"success": True})


# ── API: Rebalancing recommendations ─────────────────────────────────────────


@app.route("/api/rebalance")
def get_rebalance():
    db = get_db()
    holdings = db.execute("SELECT * FROM holdings").fetchall()
    targets = db.execute("SELECT * FROM target_allocations").fetchall()

    total_value = sum(h["current_value"] for h in holdings)

    current: dict[str, float] = {}
    for h in holdings:
        current.setdefault(h["asset_type"], 0)
        current[h["asset_type"]] += h["current_value"]

    recommendations = []
    for t in targets:
        atype = t["asset_type"]
        target_pct = t["target_percentage"]
        curr_val = current.get(atype, 0)
        curr_pct = (curr_val / total_value * 100) if total_value else 0
        target_val = total_value * target_pct / 100
        diff = target_val - curr_val
        recommendations.append(
            {
                "asset_type": atype,
                "current_value": curr_val,
                "current_pct": curr_pct,
                "target_pct": target_pct,
                "target_value": target_val,
                "difference": diff,
                "action": "Buy" if diff > 1 else "Sell" if diff < -1 else "Hold",
            }
        )

    return jsonify(
        {
            "total_value": total_value,
            "recommendations": sorted(recommendations, key=lambda x: x["asset_type"]),
        }
    )


# ── API: CSV export ───────────────────────────────────────────────────────────


@app.route("/api/export/csv")
def export_csv():
    holdings = get_db().execute(
        "SELECT * FROM holdings ORDER BY asset_type, name"
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Name", "Ticker", "Asset Type", "Shares",
            "Cost Basis ($)", "Current Value ($)",
            "Gain/Loss ($)", "Gain/Loss (%)",
            "Purchase Date", "Notes",
        ]
    )
    for h in holdings:
        gain = h["current_value"] - h["cost_basis"]
        gain_pct = (gain / h["cost_basis"] * 100) if h["cost_basis"] else 0
        writer.writerow(
            [
                h["name"],
                h["ticker"],
                h["asset_type"].replace("_", " ").title(),
                h["shares"],
                f"{h['cost_basis']:.2f}",
                f"{h['current_value']:.2f}",
                f"{gain:.2f}",
                f"{gain_pct:.2f}",
                h["purchase_date"],
                h["notes"],
            ]
        )

    filename = f"portfolio_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True)

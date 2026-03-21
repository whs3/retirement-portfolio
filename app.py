import csv
import io
import logging
import sqlite3
from datetime import datetime, timedelta

import requests
import yfinance as yf
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
            category      TEXT    NOT NULL DEFAULT '',
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
            category           TEXT    NOT NULL UNIQUE,
            target_percentage  REAL    NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    # Migrate existing databases: add category column to holdings if missing
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    # Migrate target_allocations: rename asset_type → category if needed
    cols = [row[1] for row in conn.execute("PRAGMA table_info(target_allocations)")]
    if "asset_type" in cols and "category" not in cols:
        conn.execute("ALTER TABLE target_allocations RENAME COLUMN asset_type TO category")
        conn.commit()
    # Settings table (key-value store for user configuration)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
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


@app.route("/overlap")
def overlap_page():
    return render_template("overlap.html")


@app.route("/performance")
def performance_page():
    return render_template("performance.html")


@app.route("/lookup")
def lookup_page():
    return render_template("lookup.html")


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

    if (data.get("ticker") or "").strip().upper() == "$$CASH":
        data["category"]      = "Cash"
        data["current_value"] = data.get("shares", 0)

    now = datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        """INSERT INTO holdings
               (name, ticker, asset_type, category, shares, cost_basis, current_value,
                purchase_date, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip(),
            (data.get("ticker") or "").strip().upper(),
            data["asset_type"],
            (data.get("category") or "").strip(),
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

    ticker = (data.get("ticker") or row["ticker"]).strip().upper()
    if ticker == "$$CASH":
        data["category"]      = "Cash"
        data["current_value"] = data.get("shares") if data.get("shares") is not None else row["shares"]

    now = datetime.utcnow().isoformat()
    db.execute(
        """UPDATE holdings
           SET name=?, ticker=?, asset_type=?, category=?, shares=?, cost_basis=?,
               current_value=?, purchase_date=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            (data.get("name") or row["name"]).strip(),
            (data.get("ticker") or row["ticker"]).strip().upper(),
            data.get("asset_type") or row["asset_type"],
            (data.get("category") if data.get("category") is not None else row["category"]).strip(),
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

    by_category: dict[str, float] = {}
    for h in holdings:
        cat = h["category"] or "Uncategorized"
        by_category.setdefault(cat, 0)
        by_category[cat] += h["current_value"]

    category_allocation = [
        {
            "category": cat,
            "value": val,
            "percentage": (val / total_value * 100) if total_value else 0,
        }
        for cat, val in sorted(by_category.items())
    ]

    return jsonify(
        {
            "total_value": total_value,
            "total_cost": total_cost,
            "gain_loss": gain_loss,
            "gain_loss_pct": gain_loss_pct,
            "count": len(holdings),
            "allocation": allocation,
            "category_allocation": category_allocation,
        }
    )


# ── API: Target allocations ───────────────────────────────────────────────────


@app.route("/api/allocations", methods=["GET"])
def get_allocations():
    db = get_db()
    holding_cats = db.execute(
        "SELECT DISTINCT COALESCE(NULLIF(category,''), 'Uncategorized') AS cat FROM holdings"
    ).fetchall()
    targets = db.execute("SELECT * FROM target_allocations").fetchall()
    target_map = {t["category"]: t["target_percentage"] for t in targets}
    all_cats = set(r["cat"] for r in holding_cats) | set(target_map)
    result = sorted(
        [{"category": c, "target_percentage": target_map.get(c, 0)} for c in all_cats],
        key=lambda x: x["category"],
    )
    return jsonify(result)


@app.route("/api/allocations", methods=["PUT"])
def update_allocations():
    data = request.get_json()  # [{category, target_percentage}, ...]
    total = sum(float(item["target_percentage"]) for item in data)
    if abs(total - 100) > 0.01:
        return jsonify({"error": f"Allocations must sum to 100% (currently {total:.1f}%)"}), 400

    db = get_db()
    for item in data:
        db.execute(
            """INSERT INTO target_allocations (category, target_percentage)
               VALUES (?, ?)
               ON CONFLICT(category) DO UPDATE SET target_percentage = excluded.target_percentage""",
            (item["category"], float(item["target_percentage"])),
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
        cat = h["category"] or "Uncategorized"
        current.setdefault(cat, 0)
        current[cat] += h["current_value"]

    target_map = {t["category"]: t["target_percentage"] for t in targets}
    all_cats = set(current) | set(target_map)

    recommendations = []
    for cat in all_cats:
        target_pct = target_map.get(cat, 0)
        curr_val   = current.get(cat, 0)
        curr_pct   = (curr_val / total_value * 100) if total_value else 0
        target_val = total_value * target_pct / 100
        diff       = target_val - curr_val
        recommendations.append({
            "category":      cat,
            "current_value": curr_val,
            "current_pct":   curr_pct,
            "target_pct":    target_pct,
            "target_value":  target_val,
            "difference":    diff,
            "action":        "Buy" if diff > 1 else "Sell" if diff < -1 else "Hold",
        })

    return jsonify({
        "total_value":     total_value,
        "recommendations": sorted(recommendations, key=lambda x: x["category"]),
    })


# ── API: Live prices ──────────────────────────────────────────────────────────


@app.route("/api/price/<ticker>")
def get_price(ticker):
    if ticker.upper() == "$$CASH":
        return jsonify({"price": 1.0, "name": "Cash", "category": "Cash"})
    try:
        t = yf.Ticker(ticker.upper())
        price = t.fast_info.last_price
        if price is None:
            return jsonify({"error": "Price unavailable"}), 404
        info = t.info
        name     = info.get("longName") or info.get("shortName")
        category = info.get("category") or info.get("sector") or ""
        return jsonify({"ticker": ticker.upper(), "price": price, "name": name, "category": category})
    except Exception:
        return jsonify({"error": f"Ticker '{ticker.upper()}' not found or data unavailable"}), 502


@app.route("/api/holdings/refresh-prices", methods=["POST"])
def refresh_prices():
    db = get_db()
    holdings = db.execute(
        "SELECT * FROM holdings WHERE ticker != ''"
    ).fetchall()

    updated, skipped, errors = [], [], []
    now = datetime.utcnow().isoformat()

    for h in holdings:
        if h["ticker"].upper() == "$$CASH":
            db.execute(
                "UPDATE holdings SET current_value=shares, updated_at=? WHERE id=?",
                (now, h["id"])
            )
            updated.append(h["ticker"])
            continue
        try:
            t     = yf.Ticker(h["ticker"])
            price = t.fast_info.last_price
            if price is None:
                skipped.append(h["ticker"])
                continue
            info     = t.info
            category = info.get("category") or info.get("sector") or h["category"]
            new_value = round(h["shares"] * price, 2)
            db.execute(
                "UPDATE holdings SET current_value=?, category=?, updated_at=? WHERE id=?",
                (new_value, category, now, h["id"])
            )
            audit("PRICE_UPDATE", h["ticker"], h["name"],
                  old_value=h["current_value"], new_value=new_value, price=price)
            updated.append({"ticker": h["ticker"], "price": price, "new_value": new_value, "category": category})
        except Exception as e:
            errors.append({"ticker": h["ticker"], "error": str(e)})

    db.commit()
    return jsonify({"updated": updated, "skipped": skipped, "errors": errors})


# ── API: Settings ────────────────────────────────────────────────────────────


@app.route("/api/settings", methods=["GET"])
def get_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    result = {r["key"]: r["value"] for r in rows}
    # Mask the API key in responses — return only whether it's set
    if "fmp_api_key" in result:
        result["fmp_api_key_set"] = bool(result["fmp_api_key"])
        del result["fmp_api_key"]
    return jsonify(result)


@app.route("/api/settings", methods=["PUT"])
def update_settings():
    data = request.get_json()
    db = get_db()
    for key, value in data.items():
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    db.commit()
    return jsonify({"success": True})


def _get_fmp_api_key() -> str:
    row = get_db().execute(
        "SELECT value FROM settings WHERE key='fmp_api_key'"
    ).fetchone()
    return row["value"] if row else ""


# ── Known bond ETF tickers (no equity holdings — route straight to Bond/FI) ───

_BOND_ETF_TICKERS = frozenset({
    "BND", "BNDX", "BNDW", "VGSH", "VGIT", "VGLT", "VMBS", "VTIP", "VTES",
    "SPAB", "SPSB", "SPIB", "SPLB", "SPTI", "SPTL",
    "AGG", "SHY", "IEF", "TLT", "LQD", "HYG", "JNK", "MUB", "TIP",
    "SCHZ", "SCHI",
})

# ── Ticker → provider map for known ETFs ─────────────────────────────────────

_TICKER_PROVIDER: dict[str, str] = {
    # Vanguard equity
    "VTI": "vanguard", "VOO": "vanguard", "VTV": "vanguard", "VIG": "vanguard",
    "VUG": "vanguard", "VYM": "vanguard", "VGT": "vanguard", "VEA": "vanguard",
    "VWO": "vanguard", "VXUS": "vanguard", "MGK": "vanguard", "MGV": "vanguard",
    "VB":  "vanguard", "VO":  "vanguard",  "VV": "vanguard",
    # State Street (SSGA) equity
    "SPY": "ssga", "SPDW": "ssga", "SPEM": "ssga", "SPLG": "ssga",
    # Invesco
    "QQQ": "invesco", "QQQM": "invesco",
}

# ── Provider fetchers ─────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get_etf_holdings_vanguard(ticker: str) -> list[dict]:
    """Fetch complete holdings from Vanguard's investor API (JSON, paginated)."""
    all_holdings: list[dict] = []
    start, page_size = 0, 1000
    url = (f"https://investor.vanguard.com/investment-products/etfs"
           f"/profile/api/{ticker}/portfolio-holding/stock")
    while True:
        resp = requests.get(
            url, params={"start": start, "count": page_size},
            headers=_HEADERS, timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"Vanguard API returned {resp.status_code} for {ticker}")
        entities = resp.json().get("fund", {}).get("entity", [])
        for h in entities:
            if h.get("ticker") and h.get("percentWeight") is not None:
                all_holdings.append({
                    "symbol": str(h["ticker"]),
                    "name":   h.get("longName", h["ticker"]),
                    "weight": float(h["percentWeight"]) / 100,
                })
        if len(entities) < page_size:
            break
        start += page_size
    if not all_holdings:
        raise ValueError(f"No equity holdings from Vanguard for {ticker}")
    return all_holdings


def _get_etf_holdings_ssga(ticker: str) -> list[dict]:
    """Fetch complete holdings from State Street SSGA (XLSX download)."""
    import openpyxl
    url = (f"https://www.ssga.com/us/en/intermediary/etfs/library-content"
           f"/products/fund-data/etfs/us/holdings-daily-us-en-{ticker.lower()}.xlsx")
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    if resp.status_code != 200:
        raise ValueError(f"SSGA returned {resp.status_code} for {ticker}")

    wb   = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    # Row 5 (index 4) = column headers; rows 6+ = data
    hdr        = list(rows[4])
    name_idx   = hdr.index("Name")
    ticker_idx = hdr.index("Ticker")
    weight_idx = hdr.index("Weight")

    result = []
    for row in rows[5:]:
        sym = row[ticker_idx]
        wt  = row[weight_idx]
        if sym and wt is not None:
            try:
                result.append({
                    "symbol": str(sym).strip(),
                    "name":   str(row[name_idx]).strip() if row[name_idx] else str(sym),
                    "weight": float(wt) / 100,
                })
            except (ValueError, TypeError):
                pass
    if not result:
        raise ValueError(f"No equity holdings from SSGA for {ticker}")
    return result


def _get_etf_holdings_invesco(ticker: str) -> list[dict]:
    """Fetch complete holdings from Invesco's API (JSON)."""
    url  = (f"https://dng-api.invesco.com/cache/v1/accounts/en_US"
            f"/shareclasses/{ticker}/holdings/fund")
    resp = requests.get(
        url,
        params={"idType": "ticker", "interval": "monthly", "productType": "ETF"},
        headers=_HEADERS, timeout=15,
    )
    if resp.status_code != 200:
        raise ValueError(f"Invesco API returned {resp.status_code} for {ticker}")
    holdings = resp.json().get("holdings", [])
    if not holdings:
        raise ValueError(f"No holdings from Invesco for {ticker}")
    return [
        {
            "symbol": h["ticker"],
            "name":   h.get("issuerName", h["ticker"]),
            "weight": float(h["percentageOfTotalNetAssets"]) / 100,
        }
        for h in holdings
        if h.get("ticker") and h.get("percentageOfTotalNetAssets") is not None
    ]


_PROVIDER_FETCHERS = {
    "vanguard": _get_etf_holdings_vanguard,
    "ssga":     _get_etf_holdings_ssga,
    "invesco":  _get_etf_holdings_invesco,
}

_SOURCE_LABELS = {
    "vanguard": "Vanguard",
    "ssga":     "State Street",
    "invesco":  "Invesco",
    "fmp":      "FMP",
    "yfinance": "yfinance",
}

# ── FMP fetcher ───────────────────────────────────────────────────────────────

def _get_etf_holdings_fmp(ticker: str, api_key: str) -> list[dict]:
    """Fetch full ETF holdings from Financial Modeling Prep (stable endpoint).

    Returns list of {symbol, name, weight} where weight is a decimal (0–1).
    Raises on any failure so the caller can fall back to yfinance.
    """
    url  = "https://financialmodelingprep.com/stable/etf/holdings"
    resp = requests.get(url, params={"symbol": ticker, "apikey": api_key}, timeout=10)
    if resp.status_code == 402:
        raise ValueError("FMP plan does not include ETF holdings (paid feature)")
    resp.raise_for_status()
    data = resp.json()
    if not data or isinstance(data, dict):   # error response is a dict
        raise ValueError(data.get("Error Message", "Empty response from FMP"))
    # weightPercentage may be a true percentage (7.12) or decimal (0.0712) depending on plan
    sample_weight = float(data[0].get("weightPercentage") or 0)
    scale = 100.0 if sample_weight > 1.0 else 1.0
    return [
        {
            "symbol": item["asset"],
            "name":   item.get("name", item["asset"]),
            "weight": float(item.get("weightPercentage") or 0) / scale,
        }
        for item in data
        if item.get("asset") and item.get("weightPercentage") is not None
    ]


def _get_etf_holdings_yfinance(ticker: str) -> list[dict]:
    """Fetch top ETF holdings from yfinance.

    Returns list of {symbol, name, weight} where weight is a decimal (0–1).
    Raises on any failure.
    """
    top = yf.Ticker(ticker).funds_data.top_holdings
    if top is None or top.empty:
        raise ValueError("No top-holdings data returned")
    return [
        {
            "symbol": str(symbol),
            "name":   str(row["Name"]),
            "weight": float(row["Holding Percent"]),
        }
        for symbol, row in top.iterrows()
    ]


def _get_etf_holdings(ticker: str, fmp_api_key: str) -> tuple[list[dict], str]:
    """Return (holdings, source).

    Priority:
      1. Known provider (Vanguard / SSGA / Invesco) — full holdings, free
      2. FMP — full holdings if paid key present
      3. yfinance — top-N holdings fallback
    """
    provider = _TICKER_PROVIDER.get(ticker)
    if provider:
        return _PROVIDER_FETCHERS[provider](ticker), provider

    if fmp_api_key:
        try:
            return _get_etf_holdings_fmp(ticker, fmp_api_key), "fmp"
        except Exception:
            pass

    return _get_etf_holdings_yfinance(ticker), "yfinance"


# ── API: Stock overlap ────────────────────────────────────────────────────────


@app.route("/api/overlap")
def get_overlap():
    """
    Break every holding down to its underlying individual stocks and accumulate
    the dollar value of each stock across the whole portfolio.

    - stock       → counted at full current_value
    - etf / mutual_fund → top holdings fetched via yfinance; remainder bucketed
                          as "Other Holdings"
    - bond        → counted as-is under "Bond: <name>"
    - cash        → excluded
    """
    holdings_rows = get_db().execute("SELECT * FROM holdings").fetchall()

    # Summarise by ticker (same approach as the dashboard) so we only call
    # yfinance once per unique ticker regardless of how many rows share it.
    summarised: dict[str, dict] = {}   # ticker/key → {name, asset_type, value}
    for h in holdings_rows:
        if h["asset_type"] == "cash":
            continue
        key = (h["ticker"] or h["name"]).upper()
        if key not in summarised:
            summarised[key] = {
                "name":       h["name"],
                "asset_type": h["asset_type"],
                "value":      0.0,
            }
        summarised[key]["value"] += h["current_value"]

    fmp_api_key = _get_fmp_api_key()

    stock_totals: dict[str, dict] = {}   # key → {name, value}
    other_value = 0.0
    other_breakdown: list[dict] = []    # per-ETF contributions to Other Holdings
    bond_fi_value = 0.0
    errors = []

    def _add(key: str, name: str, value: float):
        if key not in stock_totals:
            stock_totals[key] = {"name": name, "value": 0.0}
        stock_totals[key]["value"] += value

    for ticker, info in summarised.items():
        asset_type = info["asset_type"]
        total_value = info["value"]

        if asset_type == "stock":
            _add(ticker, info["name"], total_value)

        elif asset_type in ("etf", "mutual_fund"):
            # Known bond ETFs have no equity holdings — bucket silently
            if ticker in _BOND_ETF_TICKERS:
                bond_fi_value += total_value
                continue

            try:
                holdings, source = _get_etf_holdings(ticker, fmp_api_key)

                total_pct = 0.0
                for h in holdings:
                    total_pct += h["weight"]
                    _add(h["symbol"], h["name"], total_value * h["weight"])

                # Portion not represented in returned holdings
                remaining = max(0.0, 1.0 - total_pct)
                remainder_value = total_value * remaining
                other_value += remainder_value
                if remainder_value > 0.01:
                    other_breakdown.append({
                        "ticker":      ticker,
                        "name":        info["name"],
                        "covered_pct": round(total_pct * 100, 1),
                        "other_pct":   round(remaining * 100, 1),
                        "other_value": round(remainder_value, 2),
                        "source":      _SOURCE_LABELS.get(source, source),
                    })

            except Exception as exc:
                errors.append({"ticker": ticker, "error": str(exc)})
                bond_fi_value += total_value

        elif asset_type == "bond":
            bond_fi_value += total_value

    if bond_fi_value > 0.01:
        _add("__BOND_FI__", "Bond / Fixed Income", bond_fi_value)
    if other_value > 0.01:
        _add("__OTHER__", "Other Holdings", other_value)

    result = [
        {"ticker": k, "name": v["name"], "value": round(v["value"], 2)}
        for k, v in stock_totals.items()
    ]
    result.sort(key=lambda x: x["value"], reverse=True)

    total = sum(r["value"] for r in result)
    for r in result:
        r["percentage"] = round((r["value"] / total * 100) if total else 0, 2)

    other_breakdown.sort(key=lambda x: x["other_value"], reverse=True)
    return jsonify({
        "stocks":          result,
        "total":           round(total, 2),
        "errors":          errors,
        "other_breakdown": other_breakdown,
    })


# ── API: Performance (12-month growth) ───────────────────────────────────────


@app.route("/api/performance")
def get_performance():
    """
    Return daily portfolio values for the past 12 months calculated as
    current shares × historical closing prices.

    Holdings without a ticker (or whose history can't be fetched) are included
    as a constant contribution equal to their current_value.
    """
    import pandas as pd

    holdings_rows = get_db().execute("SELECT * FROM holdings").fetchall()

    # DB total matches the dashboard exactly
    db_total = sum(h["current_value"] for h in holdings_rows)

    # Sum shares by ticker; accumulate untickered value as constant
    shares_by_ticker: dict[str, float] = {}
    constant_value = 0.0

    for h in holdings_rows:
        ticker = (h["ticker"] or "").strip().upper()
        if not ticker or ticker == "$$CASH":
            constant_value += h["current_value"]
            continue
        shares_by_ticker[ticker] = shares_by_ticker.get(ticker, 0.0) + h["shares"]

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=375)   # a little extra so we can trim to 365

    if not shares_by_ticker:
        return jsonify({
            "dates": [], "values": [], "summary": {},
            "untracked": [], "untracked_value": round(constant_value, 2),
        })

    tickers_list = list(shares_by_ticker.keys())
    raw = yf.download(
        tickers_list,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        multi_level_index=True,
    )

    if raw.empty:
        return jsonify({
            "dates": [], "values": [], "summary": {},
            "untracked": tickers_list, "untracked_value": round(constant_value, 2),
        })

    close = raw["Close"]   # DataFrame: index=Date, columns=tickers

    # Build portfolio value series
    portfolio   = pd.Series(0.0, index=close.index)
    untracked   = []
    for ticker, shares in shares_by_ticker.items():
        if ticker in close.columns:
            portfolio = portfolio + close[ticker].ffill() * shares
        else:
            untracked.append(ticker)
            constant_value += shares_by_ticker[ticker]   # treat as constant

    portfolio = portfolio + constant_value
    portfolio = portfolio.dropna()

    # Trim to last 365 calendar days
    cutoff    = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    portfolio = portfolio[portfolio.index >= cutoff]

    if portfolio.empty:
        return jsonify({
            "dates": [], "values": [], "summary": {},
            "untracked": untracked, "untracked_value": round(constant_value, 2),
        })

    dates  = [d.strftime("%Y-%m-%d") for d in portfolio.index]
    values = [round(float(v), 2)     for v in portfolio.values]

    start_val = values[0]
    end_val   = values[-1]
    gain      = end_val - start_val
    gain_pct  = (gain / start_val * 100) if start_val else 0
    peak_val  = max(values)
    trough    = min(values)

    # Monthly breakdown: first and last trading day of each calendar month
    portfolio.index = pd.to_datetime(portfolio.index)
    monthly_first = portfolio.resample("MS").first()
    monthly_last  = portfolio.resample("MS").last()
    monthly = []
    for month in monthly_last.index:
        m_start = float(monthly_first.get(month, monthly_last[month]))
        m_end   = float(monthly_last[month])
        m_gain  = m_end - m_start
        m_pct   = (m_gain / m_start * 100) if m_start else 0
        monthly.append({
            "month":      month.strftime("%b %Y"),
            "start":      round(m_start, 2),
            "end":        round(m_end, 2),
            "gain":       round(m_gain, 2),
            "gain_pct":   round(m_pct, 2),
        })

    db_gain     = db_total - start_val
    db_gain_pct = (db_gain / start_val * 100) if start_val else 0

    return jsonify({
        "dates":  dates,
        "values": values,
        "summary": {
            "start_value":  round(start_val, 2),
            "end_value":    round(db_total, 2),      # matches dashboard
            "gain":         round(db_gain, 2),
            "gain_pct":     round(db_gain_pct, 2),
            "peak_value":   round(peak_val, 2),
            "trough_value": round(trough, 2),
        },
        "monthly":          monthly,
        "untracked":        untracked,
        "untracked_value":  round(constant_value, 2),
    })


# ── API: Symbol lookup ───────────────────────────────────────────────────────


@app.route("/api/lookup/<ticker>")
def lookup_ticker(ticker):
    symbol = ticker.strip().upper()
    try:
        t    = yf.Ticker(symbol)
        hist = t.history(period="1y")
        if hist.empty:
            return jsonify({"error": f"No price history found for '{symbol}'"}), 404

        info       = t.info
        name       = info.get("longName") or info.get("shortName") or symbol
        quote_type = (info.get("quoteType") or "").lower()   # equity, etf, mutualfund, …

        dates  = [d.strftime("%Y-%m-%d") for d in hist.index]
        prices = [round(float(p), 2) for p in hist["Close"]]

        start_price   = prices[0]
        current_price = prices[-1]
        change        = current_price - start_price
        change_pct    = (change / start_price * 100) if start_price else 0

        # Top holdings for funds / ETFs
        top_holdings = []
        if quote_type in ("etf", "mutualfund"):
            try:
                # Try provider first (uses existing helper); limit to 10
                holdings, _ = _get_etf_holdings(symbol, _get_fmp_api_key())
                for h in holdings[:10]:
                    top_holdings.append({
                        "symbol":  h["symbol"],
                        "name":    h["name"],
                        "weight":  round(h["weight"] * 100, 2),
                    })
            except Exception:
                try:
                    top = t.funds_data.top_holdings
                    if top is not None and not top.empty:
                        for sym, row in top.head(10).iterrows():
                            top_holdings.append({
                                "symbol": str(sym),
                                "name":   str(row["Name"]),
                                "weight": round(float(row["Holding Percent"]) * 100, 2),
                            })
                except Exception:
                    pass

        return jsonify({
            "symbol":       symbol,
            "name":         name,
            "quote_type":   quote_type,
            "dates":        dates,
            "prices":       prices,
            "current_price": round(current_price, 2),
            "start_price":   round(start_price, 2),
            "change":        round(change, 2),
            "change_pct":    round(change_pct, 2),
            "week52_high":   info.get("fiftyTwoWeekHigh"),
            "week52_low":    info.get("fiftyTwoWeekLow"),
            "top_holdings":  top_holdings,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


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

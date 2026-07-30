# Retirement Portfolio Tracker

A self-hosted web app for tracking retirement investment holdings. Built with **Flask**, **SQLite**, and plain **HTML/CSS/JavaScript** (Chart.js for charts). No frontend build step.

The backend is organized as a `portfolio` Python package with an app factory, blueprints, and service modules. `app.py` is a thin entry point so `python app.py` and existing systemd units keep working.

---

## Features

| Page | Description |
|------|-------------|
| **Dashboard** | Total value, cost basis, gain/loss; allocation by asset type, category, owner, and account type; holdings summary; one-click price refresh |
| **Holdings** | Add, edit, delete positions (stocks, bonds, ETFs, mutual funds, cash); owner and account type; sell via negative amounts or **Sell all**; live Yahoo Finance prices; search/sort/filter |
| **Performance** | Portfolio value over time (3M / 6M / YTD / 12M); stacked category breakdown; individual holdings % change; monthly gain/loss table |
| **Price Lookup** | 12-month history for any ticker; S&P 500 and NASDAQ on open; analyst data for stocks; fund family, category, AUM, expense ratio, tracked index for funds |
| **Overlap** | Break ETFs/funds into underlying stocks and show concentration across the whole portfolio |
| **Rebalance** | Category target allocations with Buy / Sell / Hold recommendations |
| **Insights** | Analyst consensus, sentiment mix, expense/valuation signals, and high-level recommendations |
| **Audit Log** | Searchable history of adds, edits, deletes, and price updates |
| **CSV Export** | Download all holdings as a spreadsheet |

---

## Requirements

- **Python 3.10+** (developed/CI-tested on 3.13)
- SQLite (included with Python)
- Network access for market data (Yahoo Finance via `yfinance`; optional FMP and issuer ETF APIs)

---

## Quick start

```bash
git clone https://github.com/whs3/retirement-portfolio.git
cd retirement-portfolio

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

Open [http://localhost:5000](http://localhost:5000). The database file `portfolio.db` is created automatically on first run.

Alternative (Flask CLI, debug reloader):

```bash
export FLASK_ENV=development
flask --app app run --debug
```

### Sample data

Load 18 sample holdings and category target allocations:

```bash
python seed.py
```

Safe to re-run: existing holdings (matched by name + asset type) are skipped, and existing target allocations are left unchanged.

---

## Configuration

Settings can be provided via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | random per process | Flask/CSRF secret. **Set a fixed value in production** so restarts do not invalidate open sessions |
| `PORTFOLIO_DATABASE` | `portfolio.db` | SQLite database path (relative to working directory unless absolute) |
| `PORTFOLIO_AUDIT_LOG` | `portfolio_audit.log` | Append-only audit log path |
| `FLASK_ENV` | (unset) | Set to `development` to enable debug mode when using `python app.py` |
| `TZ` | system | IANA timezone used for display timestamps (e.g. `America/New_York`) |

Example:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export PORTFOLIO_DATABASE=/var/lib/retirement-portfolio/portfolio.db
python app.py
```

### Optional: Financial Modeling Prep API key

By default, ETF holdings come from issuer APIs (Vanguard, State Street, Invesco) when known, otherwise Yahoo Finance top holdings. For broader full-holdings coverage, store a [Financial Modeling Prep](https://financialmodelingprep.com/) API key in the app **Settings** (stored in SQLite; never returned in plain text by the API).

---

## Running tests

Tests use a temporary SQLite database per test and **mock** external market data (no network required).

```bash
pip install -r requirements-dev.txt
pytest
```

Useful variants:

```bash
pytest -v                          # verbose
pytest --cov=portfolio --cov-report=term-missing   # coverage
pytest tests/test_holdings_api.py  # single file
```

The suite covers validators, fund-index parsing, holdings CRUD / sell-all, summary & rebalance, settings, audit, security headers / LAN allowlist, CSV export, and mocked prices, performance, overlap, and lookup services.

CI (GitHub Actions) runs syntax checks, import checks, and `pytest` on pushes and pull requests to `main`.

---

## Project structure

```text
app.py                      # Entry point: create_app() + run
portfolio/                  # Application package
  __init__.py               # App factory
  config.py                 # Config / TestConfig / env vars
  db.py                     # SQLite connection + schema migrations
  validators.py             # Ticker regex, numeric parsing
  security.py               # LAN allowlist + security headers
  extensions.py             # CSRF + rate limiter
  timezone_util.py          # Server IANA timezone detection
  routes/                   # Flask blueprints (HTTP pages + JSON APIs)
  services/                 # Business logic & external data
seed.py                     # Sample holdings and target allocations
tests/                      # pytest suite
templates/                  # Jinja2 pages (base + one per feature)
static/css/                 # Stylesheet
static/js/                  # Per-page frontend (fetch + Chart.js)
requirements.txt            # Runtime dependencies
requirements-dev.txt        # pytest, coverage, …
retirement-portfolio.service  # Example systemd unit
.github/workflows/ci.yml
```

### Package layout (backend)

| Area | Responsibility |
|------|----------------|
| `portfolio/routes/` | Page routes and `/api/*` endpoints |
| `portfolio/services/` | Prices, ETF holdings, performance series, overlap, insights, lookup, audit logging |
| `portfolio/db.py` | `get_db()`, `init_db()`, migrations (`owner`, `account_type`, settings table) |
| `portfolio/validators.py` | Shared input validation at API boundaries |

Frontend stays vanilla JS: one template + one script per page, shared nav and CSRF helper in `templates/base.html`.

---

## API overview

All JSON APIs are same-origin. Mutating requests need a CSRF token (`X-CSRFToken`); the frontend attaches it automatically.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/holdings` | List holdings |
| POST | `/api/holdings` | Create holding |
| PUT | `/api/holdings/<id>` | Update holding |
| DELETE | `/api/holdings/<id>` | Delete holding |
| POST | `/api/holdings/sell-all` | Offset a position to zero (ticker + owner + account) |
| POST | `/api/holdings/refresh-prices` | Bulk price refresh (rate limited) |
| GET | `/api/portfolio/summary` | Totals and allocation breakdowns |
| GET/PUT | `/api/allocations` | Target allocations (must sum to 100% on PUT) |
| GET | `/api/rebalance` | Buy / Sell / Hold recommendations |
| GET | `/api/performance` | Daily history + category/holding series (rate limited) |
| GET | `/api/overlap` | Underlying stock exposure (rate limited) |
| GET | `/api/insights` | Analyst / market insights (rate limited) |
| GET | `/api/lookup/<ticker>` | Price history and metadata |
| GET | `/api/price/<ticker>` | Current price for one ticker |
| GET/PUT | `/api/settings` | App settings (API keys masked on GET) |
| GET | `/api/audit` | Parsed audit log entries |
| GET | `/api/export/csv` | CSV download |

---

## Security model

Designed for **home-lab / LAN** use, not public internet exposure:

- **Network allowlist** — only `127.0.0.1`, `::1`, and `192.168.*` clients; others get HTTP 403
- **CSRF protection** — Flask-WTF on state-changing requests
- **Rate limits** — expensive endpoints (price refresh, overlap, performance, insights)
- **Input validation** — ticker format and numeric fields (NaN/inf rejected; sells allow negatives)
- **Response headers** — `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`
- **Settings** — FMP API key stored server-side; API only reports whether it is set

If you reverse-proxy or expose the app beyond the LAN, add authentication and HTTPS yourself; the built-in allowlist is not a substitute for a proper auth layer.

---

## Running as a systemd service

An example unit ships as `retirement-portfolio.service`. Install and point it at **this** checkout and virtualenv:

```ini
[Unit]
Description=Retirement Portfolio Flask App
After=network.target

[Service]
Type=simple
User=bill
WorkingDirectory=/home/bill/sandbox/grok/retirement-portfolio
Environment=PATH=/home/bill/sandbox/grok/retirement-portfolio/.venv/bin
Environment=SECRET_KEY=replace-with-a-long-random-secret
ExecStart=/home/bill/sandbox/grok/retirement-portfolio/.venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp retirement-portfolio.service /etc/systemd/system/
# or: sudo systemctl edit --full retirement-portfolio.service
sudo systemctl daemon-reload
sudo systemctl enable --now retirement-portfolio.service
sudo systemctl status retirement-portfolio.service
```

Notes:

- `WorkingDirectory` controls where `portfolio.db` and `portfolio_audit.log` are created (unless absolute paths are set via env).
- The stock unit runs the Flask development server. For heavier use, consider gunicorn/waitress behind a reverse proxy.
- Always set a stable `SECRET_KEY` under systemd so CSRF tokens survive restarts.

---

## Runtime files

Created automatically; gitignored:

| File | Description |
|------|-------------|
| `portfolio.db` | SQLite database (holdings, target allocations, settings) |
| `portfolio_audit.log` | Append-only audit trail of mutations |

Back up `portfolio.db` regularly if you rely on this for real balances.

---

## Data sources

| Source | Used for |
|--------|----------|
| **Yahoo Finance** (`yfinance`) | Prices, history, fund metadata, analyst data, top ETF holdings fallback |
| **Vanguard / SSGA / Invesco** | Full equity holdings for known tickers (overlap analysis) |
| **Financial Modeling Prep** (optional) | Full ETF holdings when an API key is configured |

Price refresh prefers `regularMarketPrice`, then `fast_info.last_price`, so mutual fund NAVs match what Yahoo shows when possible.

---

## Development notes

- **App factory** — `from portfolio import create_app`; tests pass a config dict (temp DB, CSRF off, rate limits off).
- **Python changes** require a server restart; Jinja templates reload when `TEMPLATES_AUTO_RELOAD` is on (default).
- **Asset types** stored as: `stock`, `bond`, `etf`, `mutual_fund`, `cash`.
- **Sells** can be negative share/cost/value rows, or a single offsetting row via **Sell all** for a ticker + owner + account type.
- Performance charts approximate history as *current net shares × historical prices* (plus constant value for cash / unpriced holdings). They are not a full transaction-ledger backtest.

---

## License

Use and modify for personal retirement tracking as you see fit. Review third-party data provider terms (Yahoo Finance, FMP, fund issuers) before redistributing or commercializing.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Workflow

After any backend/Flask changes (routes, data processing, API endpoints), always restart the Flask dev server before testing or declaring the task complete.


## Libraries & Gotchas

When working with Chart.js, test visual changes by verifying the actual rendered output matches expectations. Don't assume API behavior for properties like itemSort, tooltip callbacks, or tick filtering—check the docs or existing code first.

## Project Overview

This is a Flask + JavaScript retirement portfolio app. Stack: Python/Flask backend, vanilla JS frontend with Chart.js for visualizations, HTML/CSS templates. External API: Financial Modeling Prep (FMP).

## Commands

```bash
# Install dependencies (Python 3.x required; SQLite is built-in)
pip install -r requirements.txt

# Run the development server (auto-creates portfolio.db on first run)
python app.py
# or
flask --app app run --debug

# The app is then available at http://localhost:5000
```

There is no test suite or linter configured yet.

`portfolio_audit.log` is written to the project root at runtime — add it to `.gitignore` alongside `portfolio.db`.

## Architecture

Single-file Flask backend (`app.py`) with a plain HTML/JS frontend. No build step.

**Backend** (`app.py`)
- All Flask routes, DB helpers, and business logic live in one file.
- SQLite database (`portfolio.db`) is created automatically via `init_db()` at module import time.
- `get_db()` / `close_db()` use Flask's `g` object for per-request connection caching.
- Two tables: `holdings` and `target_allocations`.
- `TEMPLATES_AUTO_RELOAD = True` — template changes are picked up without restarting the server (Python code changes still require a restart).

**Security**
- `localhost_only()` before_request hook — rejects any request not from 127.0.0.1 / ::1.
- `security_headers()` after_request hook — adds X-Content-Type-Options, X-Frame-Options, X-XSS-Protection.
- Flask-WTF `CSRFProtect` with `X-CSRFToken` header; a global fetch interceptor in `base.html` attaches the token automatically to all mutating requests.
- Flask-Limiter rate-limits expensive endpoints (refresh-prices, overlap, performance: 10/hour or 10/minute).
- `_VALID_TICKER` regex validates ticker symbols on all routes that accept them.
- `_parse_positive_float()` rejects NaN, inf, and negative values for numeric fields (used for settings, allocations, etc.).
- `_parse_float()` rejects NaN and inf but allows negatives — used for holdings shares/cost_basis/current_value to support sell transactions.
- Settings updates use an `_ALLOWED_SETTINGS` whitelist.

**API surface**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/holdings` | List all holdings |
| POST | `/api/holdings` | Create holding |
| PUT | `/api/holdings/<id>` | Update holding |
| DELETE | `/api/holdings/<id>` | Delete holding |
| GET | `/api/portfolio/summary` | Totals + allocation breakdown |
| GET | `/api/allocations` | Target allocations |
| PUT | `/api/allocations` | Save target allocations (must sum to 100%) |
| GET | `/api/rebalance` | Buy/Sell/Hold recommendations |
| GET | `/api/export/csv` | Download holdings as CSV |
| GET | `/api/audit` | Audit log entries |
| GET | `/api/price/<ticker>` | Current price for a single ticker (yfinance) |
| POST | `/api/holdings/refresh-prices` | Bulk-refresh prices for all holdings |
| GET | `/api/settings` | Read app settings (e.g. FMP API key status) |
| PUT | `/api/settings` | Save app settings |
| GET | `/api/lookup/<ticker>` | 12-month price history + metadata, analyst data, fund info, benchmark |
| GET | `/api/overlap` | ETF/fund holdings overlap analysis across portfolio |
| GET | `/api/performance` | Daily portfolio value history + per-holding series + per-category series |

**Frontend**
- `templates/base.html` — shared nav, Chart.js CDN import, CSRF meta tag, server-timezone meta tag, global fetch interceptor.
- One template + one JS file per page: `dashboard`, `holdings`, `rebalance`, `audit`, `lookup`, `overlap`, `performance`.
- No framework; fetch API calls the JSON endpoints above.
- Chart.js (loaded from jsDelivr CDN) renders charts throughout the app.

**Page summaries**
| Page | Template | JS | Description |
|------|----------|----|-------------|
| Dashboard | `dashboard.html` | — | Asset allocation doughnut + portfolio totals |
| Holdings | `holdings.html` | `holdings.js` | CRUD table for all holdings; inline price refresh; supports sell transactions via negative shares/cost_basis/current_value; Ticker Symbol is first field with auto-focus and auto-fetch on input (600 ms debounce); shares support up to 6 decimal places |
| Rebalance | `rebalance.html` | — | Buy/Sell/Hold recommendations vs target allocations |
| Audit | `audit.html` | — | Audit log with search/filter |
| Lookup | `lookup.html` | `lookup.js` | Price history chart for any ticker; auto-loads ^GSPC + ^IXIC on open; analyst recommendations for stocks; fund info + tracked index for ETFs/funds; 1M/3M/6M/YTD/12M period selector on both charts |
| Overlap | `overlap.html` | `overlap.js` | ETF holdings overlap — doughnut chart + full table |
| Performance | `performance.html` | `performance.js` | Portfolio value over time with 3M/6M/YTD/12M period selector; stacked category breakdown chart; individual holdings % change chart; monthly gain/loss table |

**Asset types** (stored as-is in the DB): `stock`, `bond`, `etf`, `mutual_fund`.

**External data sources**
- `yfinance` — price history, ETF top-holdings, analyst recommendations, fund metadata (default).
- Financial Modeling Prep (FMP) — full ETF holdings when an API key is configured via Settings.

**Key backend helpers**
- `_detect_iana_timezone()` — detects the server's IANA timezone (e.g. `America/New_York`) from `/etc/timezone`, `/etc/localtime` symlink, or `TZ` env var; result is cached in `_SERVER_TIMEZONE` and injected into all templates via a context processor so frontend timestamps display in the server's local timezone.
- `_get_ticker_category(ticker, asset_type)` — returns Morningstar category (ETF/fund) or sector (stock); results cached in `_category_cache` for the server session to avoid repeat API calls.
- `_extract_fund_index(description)` — uses regex to extract the tracked index name from a fund's description text; maps common index names to yfinance tickers via `_INDEX_TICKER_MAP`.
- `_parse_positive_float(value, field_name)` — validates numeric input at API boundaries; rejects negatives.
- `_parse_float(value, field_name)` — like `_parse_positive_float` but allows negatives; used for holdings fields to support sell transactions.

**Lookup page details**
- Market Indices section auto-loads S&P 500 (`^GSPC`) and NASDAQ (`^IXIC`) on page open; normalized % change chart with 1M/3M/6M/YTD/12M period buttons.
- Ticker lookup supports portfolio dropdown or free-text entry; uses `_lookupSeq` counter to discard stale async responses.
- Analyst section (stocks only): consensus badge, 1–5 scale marker, price targets, summary narrative, recent analyst actions table.
- Fund Information section (ETFs/mutual funds): fund family, category, AUM, net expense ratio, YTD return (calculated from price history, not the stale yfinance field), 3-year and 5-year avg returns, tracked index name and index YTD/1-year returns (where mappable), fund description.

**Performance page details**
- Period selector (3M / 6M / YTD / 12M) filters all charts, summary cards, and monthly table simultaneously.
- Summary cards update labels dynamically (e.g. "Value 3 Months Ago", "3-Month Gain / Loss").
- Category breakdown: stacked area chart grouped by Morningstar category or sector; categories fetched in parallel via `ThreadPoolExecutor` and cached in `_category_cache`.
- Individual holdings chart: normalized % change from period start so holdings of different sizes are directly comparable; Select All / Unselect All buttons; solid filled legend boxes and tooltip swatches.
- Category chart: Select All / Unselect All buttons; y-axis starts at zero for accurate proportional display.

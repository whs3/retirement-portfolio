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

```bash
# Run the test suite (isolated temp DB; no network)
pip install -r requirements-dev.txt
pytest
# or with coverage:
pytest --cov=portfolio --cov-report=term-missing
```

```bash
# Online-safe SQLite backup (timestamped under backups/)
python backup_db.py
```

Runtime files written to the project root and gitignored: `portfolio.db` (+ WAL sidecars), `portfolio_audit.log`, `audit_archive/` (archived audit-log history), `.secret_key` (if `SECRET_KEY` unset), optional `.env`, and `backups/`.

## Architecture

Package-based Flask backend with a plain HTML/JS frontend. No build step.

**Entry point** (`app.py`)
- Thin wrapper: `app = create_app()` so `python app.py` and `flask --app app run` keep working.

**Package** (`portfolio/`)
- `create_app()` in `portfolio/__init__.py` wires config, extensions, DB, security hooks, and blueprints.
- `portfolio/config.py` — env / optional `.env`, stable `SECRET_KEY` (env or `.secret_key` file), path resolution from project root.
- `portfolio/db.py` — `get_db()` / `close_db()` / `init_db()` (SQLite via Flask `g`; WAL + foreign_keys on connect).
- `portfolio/routes/` — page and JSON API blueprints (one module per area).
- `portfolio/services/` — business logic and external data (yfinance, ETF providers, performance, insights).
- `portfolio/validators.py` — ticker regex and numeric parsing.
- `portfolio/security.py` — LAN allowlist + security headers.
- SQLite database (`portfolio.db`) is created automatically via `init_db()` inside `create_app()`.
- Tables: `holdings`, `target_allocations`, `settings`, `portfolio_snapshots`, `cash_flows` (external deposits/withdrawals).
- `holdings` includes `owner` and `account_type` columns via migration in `init_db()`.
- `backup_db.py` — WAL-safe timestamped backups under `backups/`.
- `TEMPLATES_AUTO_RELOAD = True` — template changes are picked up without restarting (Python changes still need a restart).

**Security**
- `local_network_only()` before_request hook — rejects any request not from 127.0.0.1, ::1, or 192.168.x.x.
- `security_headers()` after_request hook — adds X-Content-Type-Options, X-Frame-Options, X-XSS-Protection.
- Flask-WTF `CSRFProtect` with `X-CSRFToken` header; a global fetch interceptor in `base.html` attaches the token automatically to all mutating requests. `WTF_CSRF_TIME_LIMIT` is `None` so a dashboard left open for auto-refresh does not fail after an hour; on CSRF 400 the interceptor refreshes `/api/csrf-token` and retries once. CSRF failures return JSON `{code: "csrf"}` rather than an HTML 400 page.
- Flask-Limiter rate-limits expensive endpoints (refresh-prices, overlap, performance: 10/hour or 10/minute).
- `_VALID_TICKER` regex validates ticker symbols on all routes that accept them.
- `_parse_positive_float()` rejects NaN, inf, and negative values for numeric fields (used for settings, allocations, etc.).
- `_parse_float()` rejects NaN and inf but allows negatives — used for holdings shares/cost_basis/current_value to support sell transactions.
- Settings updates use an `ALLOWED_SETTINGS` whitelist in `services/settings.py` (`fmp_api_key`, `price_refresh_minutes`, `birthdate_*`, `withdrawal_*`, `tax_rate_ordinary`, `tax_rate_gains`, `drift_threshold_pts`), each with its own parser/range check.
- A background thread (started in `create_app()`, skipped in tests) auto-refreshes prices on `price_refresh_minutes` (default 15; `0` disables). Dashboard widget reads/writes this setting.

**API surface**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/holdings` | List all holdings |
| POST | `/api/holdings` | Create holding |
| PUT | `/api/holdings/<id>` | Update holding |
| DELETE | `/api/holdings/<id>` | Delete holding |
| GET | `/api/portfolio/summary` | Totals + allocation breakdown (includes `owner_allocation` and `account_type_allocation`) |
| GET | `/api/allocations` | Target allocations |
| PUT | `/api/allocations` | Save target allocations (must sum to 100%) |
| GET | `/api/rebalance` | Buy/Sell/Hold recommendations per category with suggested trades (account + ticker) and `drift_threshold_pts` |
| GET | `/api/export/csv` | Download holdings as CSV |
| POST | `/api/import/csv` | Bulk-import holdings from a CSV matching the export format (all-or-nothing validation) |
| GET | `/api/audit` | Audit log entries from the last `RETENTION_DAYS` (7) days; older entries are archived off the live file |
| GET | `/api/price/<ticker>` | Current price for a single ticker (yfinance) |
| POST | `/api/holdings/refresh-prices` | Bulk-refresh prices for all holdings |
| GET | `/api/settings` | Read app settings (FMP key status, `price_refresh_minutes`) |
| PUT | `/api/settings` | Save app settings |
| GET | `/api/lookup/<ticker>` | 12-month price history + metadata, analyst data, fund info, benchmark |
| GET | `/api/overlap` | ETF/fund holdings overlap analysis across portfolio |
| GET | `/api/performance` | Daily portfolio value history + per-holding series + per-category series |
| GET | `/api/withdrawal` | Safe-withdrawal-rate projection; optional `rate`/`return_rate`/`inflation_rate`/`years`/`ordinary_tax`/`gains_tax` query params override persisted settings |
| POST | `/api/cash-flows` | Record a manual deposit (+) or withdrawal (−) |
| DELETE | `/api/cash-flows/<id>` | Delete a cash flow (e.g. a phantom one from a data-entry mistake) |
| GET | `/api/rmd` | Required Minimum Distribution estimate per owner (Bill/Akiko); `balance_source` (`snapshot`/`current`), `balance_as_of`, `balance_note` say which balance was used |

**Frontend**
- `templates/base.html` — shared nav, Chart.js CDN import, CSRF meta tag, server-timezone meta tag, global fetch interceptor.
- One template + one JS file per page: `dashboard`, `holdings`, `rebalance`, `audit`, `lookup`, `overlap`, `performance`, `insights`, `planning`.
- No framework; fetch API calls the JSON endpoints above.
- Chart.js (loaded from jsDelivr CDN) renders charts throughout the app.

**Page summaries**
| Page | Template | JS | Description |
|------|----------|----|-------------|
| Dashboard | `dashboard.html` | `dashboard.js` | By Owner + By Account Type doughnut charts + portfolio totals; category allocation table sorted by value; auto-refresh widget (minutes, 0 = off); drift alert banner when a category is at least the drift threshold (default 5 pts) off its rebalance target |
| Holdings | `holdings.html` | `holdings.js` | CRUD table for all holdings; Owner and Account Type filter dropdowns; search summary shows totals row; inline price refresh; Import CSV button (app's own export format, all-or-nothing); supports sell transactions via negative shares/cost_basis/current_value; Ticker Symbol is first field with auto-focus and auto-fetch on input (600 ms debounce); shares support up to 6 decimal places; second item in nav bar |
| Rebalance | `rebalance.html` | `rebalance.js` | Buy/Sell/Hold recommendations vs target allocations; "Where to trade" column naming account + ticker; editable drift threshold (saved to settings); zero-target categories filtered from chart and table |
| Audit | `audit.html` | `audit.js` | Audit log with search/filter; shows only the last 7 days (older entries are archived) |
| Lookup | `lookup.html` | `lookup.js` | Price history chart for any ticker; auto-loads ^GSPC, ^IXIC, ^MID (mid cap), ^RUT (small cap), SHY (short Treasuries) on open; analyst recommendations for stocks; fund info + tracked index for ETFs/funds; 1M/3M/6M/YTD/12M period selector on both charts |
| Overlap | `overlap.html` | `overlap.js` | ETF holdings overlap — doughnut chart + full table; Bond / Fixed Income, Other Holdings, and Unavailable buckets; per-fund coverage breakdown; result cached in `sessionStorage` until Recalculate |
| Performance | `performance.html` | `performance.js` | Portfolio value over time with 3M/6M/YTD/12M period selector; optional benchmark comparison chart (S&P 500/NASDAQ/Russell 2000/S&P MidCap 400/SHY) vs. portfolio % change; stacked category breakdown chart; individual holdings % change chart; monthly gain/loss table |
| Planning | `planning.html` | `planning.js` | Safe-withdrawal-rate projection calculator (rate/return/inflation/years + ordinary/gains tax rates, persisted via Settings) with balance-over-time chart and year-by-year table (Planned/RMD/Withdrawal/Tax/Spendable); RMD tracking table per owner (Bill/Akiko) with birthdate inputs |

**Asset types** (stored as-is in the DB): `stock`, `bond`, `etf`, `mutual_fund`.

**External data sources**
- `yfinance` — price history, ETF top-holdings, analyst recommendations, fund metadata (default).
- Financial Modeling Prep (FMP) — full ETF holdings when an API key is configured via Settings.

**Price fetching note**: Both `get_price` and `refresh_prices` use `info.get("regularMarketPrice")` as the primary price source, falling back to `fast_info.last_price` only if unavailable. `fast_info.last_price` can lag for mutual funds (e.g. NAV not yet reflected); `regularMarketPrice` matches what Yahoo Finance displays.

**Performance cash-ticker handling**: `build_performance()` does a first pass to identify `cash_tickers` — any ticker that has at least one `asset_type="cash"` entry in the DB (e.g. SPAXX). All entries for those tickers are routed to `constant_value` regardless of the individual row's asset_type. This prevents money-market funds from appearing in `shares_by_ticker` with negative share counts and no yfinance price history, which would otherwise cause an artificial portfolio drop on the one day a price becomes available. `services.snapshots.capture_snapshot()` applies the same cash-ticker rule when aggregating holdings into a daily snapshot.

**Daily performance snapshots**: `/api/performance` no longer recomputes 12 months of history from yfinance on every request. `portfolio_snapshots` (one row per calendar date) stores the actual portfolio value, per-category totals, and per-ticker values as of that day. `services.snapshots.capture_snapshot()` upserts today's row (DB-only, no network) — called after every price refresh (manual or scheduled) in `services.prices.refresh_all_prices()`, and again at the top of `GET /api/performance` so the page is always current even if auto-refresh is off. The first time the table is empty, `backfill_if_empty()` seeds ~365 days using the old current-shares × historical-price approximation from `build_performance()` (still used only for this one-time bootstrap), then immediately overwrites today with a real value. `get_performance_history()` reads purely from the DB and reshapes it into the same response `build_performance()` used to return, so `static/js/performance.js` is unchanged.

**Cash flows and investment gain** (`services/cash_flows.py`): the Performance page's "Investment Gain / Loss" is `(end value − start value) − net cash flows in (start, end]` (`period_return()`, mirrored by `_periodReturn()` in `performance.js`), so one bad flow row skews the gain by its full amount. Flows are recorded automatically: holding add / CSV import = +current value, delete / sell-all = −current value, and an edit uses `external_flow_from_share_change()` (external only when both share count and value change; a value- or cost-basis-only edit records $0, and so does a share-count-only correction with the value unchanged). Price refreshes record nothing. Exception: an edit on the **same day** a holding was added or imported goes through `revise_same_day_add_flow()`, which re-prices that original `holding_add`/`import` flow to the new value (deleting it if it becomes dust) instead of inserting an edit flow. Without that, "add with wrong sign → fix value → delete" left a phantom deposit of 2× the value (this produced a −$505K YTD gain in Oct 2026). Bad flows from before the fix are corrected by deleting them via `DELETE /api/cash-flows/<id>` (or the Performance page's flow list), after a `backup_db.py` backup.

**Audit log archiving**: `portfolio_audit.log` is an append-only, plain-text log parsed line-by-line on every `GET /api/audit` call, so letting it grow unbounded made the Audit page slow to load. `services.audit.archive_old_entries()` splits out any line older than `RETENTION_DAYS` (7) into monthly files under `audit_archive/` (e.g. `audit_archive/portfolio_audit-2026-02.log`), rewrites the live file with only the recent lines, and — since the logging `FileHandler` holds the live path open in append mode — closes and reopens that handler around the swap so subsequent writes land in the new, small file. It runs once synchronously in `create_app()` (so a long-lived log gets pruned immediately on restart) and again every 24h from a daemon thread (`services.audit.start_audit_archiver()`, skipped in tests like the price-refresh scheduler). `GET /api/audit` also filters by timestamp itself as a second line of defense for the window right after a restart, before the startup archive call would otherwise have already handled it.

**Key backend helpers** (under `portfolio/`)
- `timezone_util.detect_iana_timezone()` / `SERVER_TIMEZONE` — IANA timezone from `/etc/timezone`, `/etc/localtime`, or `TZ`; injected into templates via a context processor.
- `services.categories.get_ticker_category()` — Morningstar category (ETF/fund) or sector (stock); session-cached.
- `services.fund_index.extract_fund_index()` — regex extraction of tracked index from fund description.
- `validators.parse_positive_float()` / `parse_float()` — numeric input at API boundaries (`parse_float` allows negatives for sells).
- `services.prices.refresh_all_prices()` — shared bulk yfinance refresh used by the API and the auto-refresh scheduler; captures a daily snapshot on success.
- `services.price_scheduler.start_price_refresh_scheduler()` — daemon thread; interval from `price_refresh_minutes` (0 = off).
- `services.audit.archive_old_entries()` / `start_audit_archiver()` — moves audit-log lines older than `RETENTION_DAYS` into `audit_archive/`, keeping the live file (and `/api/audit`) fast (see above).
- `services.snapshots.capture_snapshot()` / `backfill_if_empty()` / `get_performance_history()` — daily portfolio value snapshots backing the Performance page (see above).

**Rebalance recommendations** (`services.rebalance.build_recommendations()`): one row per category; `action` is Buy/Sell only when `|current_pct - target_pct|` reaches the drift threshold (`drift_threshold_pts` setting, default 5, range 0–50, read via `services.settings.get_drift_threshold_pts()` and editable on the Rebalance page), otherwise Hold. Each row includes `positions` (holdings in that category) and, for Sells, `trades` filled in account order: taxable (`Broker`, `Cash Management`, larger lot first) → `Roth IRA` → `IRA`/`Rollover IRA` → `401k`/`403b` → unknown. Buys get no trades, just a note pointing at accounts that already hold the category.

**Dashboard drift alerts**: `dashboard.js` fetches `/api/rebalance` and shows a banner for every category whose `action` is Buy or Sell (so it uses the same configurable threshold, shown in the banner title), sorted by largest drift first, and suggests the first sell trade's ticker/account or an account that already holds the category. Zero-target categories are excluded, matching the Rebalance page's own filtering convention. The banner is hidden entirely when nothing crosses the threshold.

**Overlap page details** (`services.overlap.build_overlap()`, `services.etf_holdings`)
- Each holding is broken down to individual stocks: `stock` at full value; `etf`/`mutual_fund` via `get_etf_holdings()`, with any uncovered weight going to "Other Holdings" (`__OTHER__`); `bond` and any ticker in `BOND_ETF_TICKERS` (incl. Treasury-bill ETFs like SGOV/BIL/USFR) go straight to "Bond / Fixed Income" (`__BOND_FI__`) without a lookup.
- Cash: any ticker with at least one `asset_type="cash"` row (e.g. SPAXX) is skipped entirely, including its non-cash rows — same rule as Performance's cash-ticker handling.
- `get_etf_holdings()` source order: known provider in `TICKER_PROVIDER` (Vanguard/SSGA/Invesco) → FMP (if key set) → yfinance top-10. A failing provider falls through to the next source instead of raising (Vanguard's endpoint started returning 404 in Oct 2026; VOO/VTV/VIG now resolve via yfinance).
- If every source fails, the fund's value goes to "Unavailable" (`__UNAVAILABLE__`) and it is listed in `errors` — never into Bond / Fixed Income. The frontend maps the `__*__` bucket keys to labels via `BUCKET_LABELS` in `overlap.js`.
- With yfinance only returning top-10 holdings, "Other Holdings" is typically the largest slice; a paid FMP key gives full holdings.

**Lookup page details**
- Market Indices section auto-loads S&P 500 (`^GSPC`), NASDAQ (`^IXIC`), S&P MidCap 400 (`^MID`), Russell 2000 small cap (`^RUT`), and short-term Treasuries (`SHY`) on page open; normalized % change chart with 1M/3M/6M/YTD/12M period buttons.
- Ticker lookup supports portfolio dropdown or free-text entry; uses `_lookupSeq` counter to discard stale async responses.
- Analyst section (stocks only): consensus badge, 1–5 scale marker, price targets, summary narrative, recent analyst actions table.
- Fund Information section (ETFs/mutual funds): fund family, category, AUM, net expense ratio, YTD return (calculated from price history, not the stale yfinance field), 3-year and 5-year avg returns, tracked index name and index YTD/1-year returns (where mappable), fund description.

**Performance page details**
- Period selector (3M / 6M / YTD / 12M) filters all charts, summary cards, and monthly table simultaneously.
- Summary cards update labels dynamically (e.g. "Value 3 Months Ago", "3-Month Gain / Loss").
- Category breakdown: stacked area chart grouped by Morningstar category or sector; categories fetched in parallel via `ThreadPoolExecutor` and cached in `_category_cache`.
- Individual holdings chart: normalized % change from period start so holdings of different sizes are directly comparable; Select All / Unselect All buttons; solid filled legend boxes and tooltip swatches.
- Category chart: Select All / Unselect All buttons; y-axis starts at zero for accurate proportional display.
- Benchmark comparison chart (opt-in via a dropdown, default "None"): reuses `/api/lookup/<ticker>` (the same endpoint the Lookup page's market indices use) client-side — no backend changes. Benchmark prices only exist for trading days, so they're forward-filled onto the portfolio's snapshot dates before both series are normalized to % change from the period start and plotted together. Cached per ticker in `_benchmarkCache` for the page session; re-normalizes (no refetch) on period change.

**Planning page details** — estimates only, not tax or financial advice.
- Withdrawal projection (`services.withdrawal.project_withdrawals()`): deterministic (no Monte Carlo) "4% rule" style model — year one is next calendar year; the planned withdrawal starts at `rate% x current total portfolio value` (from `SUM(current_value)` across all holdings) and grows with inflation rather than being recalculated against the then-current balance. Each year's gross withdrawal is raised to at least the combined Bill + Akiko RMD for that calendar year (from `project_rmds()` with the same balances/return as `/api/rmd`). The withdrawal comes out first, then the remainder grows at the assumed return; once the balance hits zero it stays at zero for the rest of the projection.
- Tax estimate: holdings are split by `tax_buckets_from_holdings()` into pretax (`401k`/`403b`/`IRA`/`Rollover IRA`), roth (`Roth IRA`), and taxable (everything else). The RMD portion is drawn from pretax; anything above it comes from taxable → roth → more pretax. Pretax is taxed at `tax_rate_ordinary` (default 22%), taxable at `tax_rate_gains` (default 15%, applied to the whole draw, not just gains), Roth at 0. Each row reports `planned_withdrawal`, `rmd`, `tax`, `spendable`, and `sources`; the portfolio is reduced by the gross withdrawal. `depletion_year` is the first year (1-indexed) the balance reaches zero, or `null` if it survives the full projection window (`years`, max `MAX_YEARS` = 60).
- Assumptions (rate/return/inflation/years, plus `tax_rate_ordinary`/`tax_rate_gains`) are editable inline and persisted via `/api/settings` (`withdrawal_rate`, `withdrawal_return_rate`, `withdrawal_inflation_rate`, `withdrawal_years`) so they survive a page reload; `GET /api/withdrawal` falls back to those persisted values for any query param not supplied, defaulting to 4/6/3/30 when nothing has ever been saved.
- RMD tracking (`services.rmd.py`): IRS Uniform Lifetime Table (ages 72-120, hardcoded) is used for everyone — it does not apply if a spouse is the sole beneficiary and more than 10 years younger (Joint and Last Survivor table instead; not implemented). RMD start age follows SECURE 2.0 (72 born ≤1950, 73 born 1951-1959, 75 born 1960+).
- Only `401k`/`403b`/`IRA`/`Rollover IRA` balances count toward an owner's RMD-subject balance (`RMD_SUBJECT_ACCOUNT_TYPES` in `services/rmd.py`); `Roth IRA` and taxable accounts (`Broker`, `Cash Management`) are excluded. The app has no field distinguishing Traditional vs. Roth 401k/403b, so any `401k`/`403b` holding is assumed Traditional.
- Only owners `Bill` and `Akiko` are tracked (matches the fixed owner dropdown elsewhere in the app); `Joint`-owned holdings are excluded since RMDs apply to an individual, not a joint account. Birthdates are stored as `birthdate_bill` / `birthdate_akiko` settings (`YYYY-MM-DD`); an owner with no birthdate set shows balance only, prompting for one before any RMD figure appears.
- Balance (`services.rmd.resolve_rmd_balances()`): uses the prior December 31 `portfolio_snapshots` row's `owner_accounts_json` (owner → account type → value, captured by `capture_snapshot()`; added by migration, NULL on older/backfilled rows) when present (`balance_source` = `snapshot`); otherwise falls back to current RMD-subject balances (`balance_source` = `current`). The Uniform Lifetime factor uses the age reached on December 31 of the distribution year. Still an estimate, not exact tax preparation.

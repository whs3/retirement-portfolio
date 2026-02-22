# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

**Frontend**
- `templates/base.html` — shared nav and Chart.js CDN import.
- One template + one JS file per page: `dashboard`, `holdings`, `rebalance`.
- No framework; fetch API calls the JSON endpoints above.
- Chart.js (loaded from jsDelivr CDN) renders the doughnut chart on the dashboard and the grouped bar chart on the rebalance page.

**Asset types** (stored as-is in the DB): `stock`, `bond`, `etf`, `mutual_fund`.

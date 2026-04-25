# Retirement Portfolio Tracker

A self-hosted web app for tracking retirement investment holdings. Built with Flask, SQLite, and plain HTML/CSS/JavaScript.

## Features

- **Dashboard** — total portfolio value, cost basis, gain/loss, asset allocation and category allocation doughnut charts, holdings summary table, one-click price refresh
- **Performance** — portfolio value over time with stacked category breakdown and individual holdings % change charts; 3M / 6M / YTD / 12M period selector
- **Price Lookup** — 12-month price history for any ticker; auto-loads S&P 500 and NASDAQ on open; analyst recommendations for stocks; fund family, category, AUM, expense ratio, and tracked index for ETFs/mutual funds; 1M / 3M / 6M / YTD / 12M period selector
- **Holdings** — add, edit, and delete positions (stocks, bonds, ETFs, mutual funds) with cost basis, current value, shares, and purchase date; sell transactions via negative values; live price fetch from Yahoo Finance; searchable and sortable table
- **Overlap** — ETF/fund holdings overlap analysis across the portfolio with doughnut chart and full table
- **Rebalance** — set category-based target allocations and get buy/sell/hold recommendations
- **Audit Log** — every add, edit, delete, and price update is recorded with timestamp, ticker, and dollar amounts; searchable by date, action, ticker, and name
- **CSV Export** — download all holdings as a spreadsheet

## Setup

Python 3.x is required. SQLite is built into Python — no database setup needed.

```bash
git clone https://github.com/whs3/retirement-portfolio.git
cd retirement-portfolio
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser. The database (`portfolio.db`) is created automatically on first run.

To pre-populate the database with 18 sample holdings across all asset types and category-based target allocations:

```bash
python seed.py
```

The seed script is safe to re-run — it skips holdings that already exist and leaves existing target allocations untouched.

### Optional: Financial Modeling Prep API key

By default, ETF holdings data is sourced from Yahoo Finance. For more complete overlap analysis, add a [Financial Modeling Prep](https://financialmodelingprep.com/) API key via the Settings page.

## Project Structure

```
app.py              # Flask app — all routes and database logic
seed.py             # Loads sample holdings and target allocations into portfolio.db
templates/          # Jinja2 HTML templates (one per page + base.html)
static/css/         # Stylesheet
static/js/          # Per-page JavaScript (dashboard, holdings, lookup, overlap, performance, rebalance, audit)
requirements.txt
```

## Runtime Files

These are created automatically and excluded from version control:

| File | Description |
|------|-------------|
| `portfolio.db` | SQLite database |
| `portfolio_audit.log` | Append-only audit trail of all holding mutations |

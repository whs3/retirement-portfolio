# Retirement Portfolio Tracker

A self-hosted web app for tracking retirement investment holdings. Built with Flask, SQLite, and plain HTML/CSS/JavaScript.

## Features

- **Dashboard** — total portfolio value, cost basis, gain/loss, and an asset allocation donut chart
- **Holdings** — add, edit, and delete positions (stocks, bonds, ETFs, mutual funds) with cost basis, current value, shares, and purchase date
- **Rebalancing** — set target allocations by asset type and get buy/sell/hold recommendations
- **Audit log** — every add, edit, and delete is recorded to `portfolio_audit.log` with timestamp, ticker, and dollar amounts
- **CSV export** — download all holdings as a spreadsheet

## Setup

Python 3.x is required. SQLite is built into Python — no database setup needed.

```bash
git clone https://github.com/whs3/retirement-portfolio.git
cd retirement-portfolio
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser. The database (`portfolio.db`) is created automatically on first run with default target allocations of 60% stock / 30% bond / 5% ETF / 5% mutual fund.

To pre-populate the database with 18 sample holdings across all asset types:

```bash
python seed.py
```

The seed script is safe to re-run — it skips any holdings that already exist.

## Project Structure

```
app.py              # Flask app — all routes and database logic
seed.py             # Loads sample holdings into portfolio.db
templates/          # Jinja2 HTML templates
static/css/         # Stylesheet
static/js/          # Per-page JavaScript (dashboard, holdings, rebalance, audit)
requirements.txt
```

## Runtime Files

These are created automatically and excluded from version control:

| File | Description |
|------|-------------|
| `portfolio.db` | SQLite database |
| `portfolio_audit.log` | Append-only audit trail of all holding mutations |

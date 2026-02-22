"""
Populate portfolio.db with sample holdings and target allocations.
Existing data is left untouched; only rows that don't already exist are inserted.

Usage:
    python seed.py
"""

import sqlite3
import datetime

DB_PATH = "portfolio.db"

HOLDINGS = [
    # (name, ticker, asset_type, shares, cost_basis, current_value, purchase_date)

    # Stocks
    ("Apple Inc.",             "AAPL",  "stock",        50,  7_500,  11_200, "2021-03-15"),
    ("Microsoft Corp.",        "MSFT",  "stock",        30,  6_200,   9_800, "2020-11-10"),
    ("Alphabet Inc.",          "GOOGL", "stock",        15, 25_000,  32_400, "2020-08-10"),
    ("Amazon.com Inc.",        "AMZN",  "stock",        10, 15_200,  19_800, "2021-01-22"),
    ("NVIDIA Corp.",           "NVDA",  "stock",        20,  4_100,  17_600, "2022-03-05"),
    ("JPMorgan Chase",         "JPM",   "stock",        40,  6_800,   8_400, "2020-12-14"),
    ("Johnson & Johnson",      "JNJ",   "stock",        30,  4_500,   4_750, "2019-09-30"),

    # Bonds
    ("US Treasury Bond",       "",      "bond",          0, 20_000,  20_400, "2022-01-20"),
    ("US I Bond",              "",      "bond",          0, 10_000,  11_350, "2022-05-01"),
    ("iShares Bond ETF",       "AGG",   "bond",        100,  9_800,   9_950, "2021-08-05"),
    ("Vanguard Short-Term Bond","VBIRX","bond",          0,  8_500,   8_300, "2021-10-08"),

    # ETFs
    ("Vanguard S&P 500",       "VOO",   "etf",          40, 12_000,  15_600, "2019-06-01"),
    ("Invesco QQQ Trust",      "QQQ",   "etf",          25,  9_200,  11_800, "2021-06-18"),
    ("Vanguard Intl Stock ETF","VXUS",  "etf",          80,  4_800,   5_200, "2022-01-10"),

    # Mutual funds
    ("Fidelity 500 Fund",      "FXAIX", "mutual_fund",   0,  5_000,   6_300, "2020-04-12"),
    ("Vanguard Total Bond",    "VBTLX", "mutual_fund",   0,  8_000,   7_850, "2020-07-01"),
    ("T. Rowe Price Growth",   "PRGFX", "mutual_fund",   0,  7_500,   9_900, "2019-11-15"),
    ("Schwab Total Market",    "SWTSX", "mutual_fund",   0,  6_000,   7_400, "2021-04-20"),
]

TARGET_ALLOCATIONS = [
    ("stock",       60),
    ("bond",        30),
    ("etf",          5),
    ("mutual_fund",  5),
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.datetime.now(datetime.UTC).isoformat()

    # Ensure tables exist (mirrors init_db in app.py)
    conn.executescript("""
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
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type        TEXT    NOT NULL UNIQUE,
            target_percentage REAL    NOT NULL DEFAULT 0
        );
    """)

    inserted = 0
    for name, ticker, asset_type, shares, cost_basis, current_value, purchase_date in HOLDINGS:
        exists = conn.execute(
            "SELECT 1 FROM holdings WHERE name = ? AND asset_type = ?", (name, asset_type)
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO holdings
                       (name, ticker, asset_type, shares, cost_basis, current_value,
                        purchase_date, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                (name, ticker, asset_type, shares, cost_basis, current_value,
                 purchase_date, now, now),
            )
            inserted += 1

    for asset_type, target_pct in TARGET_ALLOCATIONS:
        conn.execute(
            """INSERT INTO target_allocations (asset_type, target_percentage)
               VALUES (?, ?)
               ON CONFLICT(asset_type) DO NOTHING""",
            (asset_type, target_pct),
        )

    conn.commit()
    conn.close()

    total = len(HOLDINGS)
    skipped = total - inserted
    print(f"Seeded {inserted} holding(s). {skipped} already existed — skipped.")


if __name__ == "__main__":
    seed()

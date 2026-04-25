"""
Populate portfolio.db with sample holdings and target allocations.
Existing data is left untouched; only rows that don't already exist are inserted.

Usage:
    python seed.py
"""

import datetime
import sqlite3

DB_PATH = "portfolio.db"

HOLDINGS = [
    # (name, ticker, asset_type, category, shares, cost_basis, current_value, purchase_date)

    # Stocks
    ("Apple Inc.",             "AAPL",  "stock",        "Technology",        50,  7_500,  11_200, "2021-03-15"),
    ("Microsoft Corp.",        "MSFT",  "stock",        "Technology",        30,  6_200,   9_800, "2020-11-10"),
    ("Alphabet Inc.",          "GOOGL", "stock",        "Communication Services", 15, 25_000, 32_400, "2020-08-10"),
    ("Amazon.com Inc.",        "AMZN",  "stock",        "Consumer Cyclical", 10, 15_200,  19_800, "2021-01-22"),
    ("NVIDIA Corp.",           "NVDA",  "stock",        "Technology",        20,  4_100,  17_600, "2022-03-05"),
    ("JPMorgan Chase",         "JPM",   "stock",        "Financial Services", 40,  6_800,  8_400, "2020-12-14"),
    ("Johnson & Johnson",      "JNJ",   "stock",        "Healthcare",        30,  4_500,   4_750, "2019-09-30"),

    # Bonds
    ("US Treasury Bond",       "",      "bond",         "Treasury",           0, 20_000,  20_400, "2022-01-20"),
    ("US I Bond",              "",      "bond",         "Treasury",           0, 10_000,  11_350, "2022-05-01"),
    ("iShares Bond ETF",       "AGG",   "bond",         "Intermediate Core Bond", 100, 9_800, 9_950, "2021-08-05"),
    ("Vanguard Short-Term Bond","VBIRX","bond",         "Short-Term Bond",    0,  8_500,   8_300, "2021-10-08"),

    # ETFs
    ("Vanguard S&P 500",       "VOO",   "etf",          "Large Blend",       40, 12_000,  15_600, "2019-06-01"),
    ("Invesco QQQ Trust",      "QQQ",   "etf",          "Large Growth",      25,  9_200,  11_800, "2021-06-18"),
    ("Vanguard Intl Stock ETF","VXUS",  "etf",          "Foreign Large Blend", 80, 4_800,  5_200, "2022-01-10"),

    # Mutual funds
    ("Fidelity 500 Fund",      "FXAIX", "mutual_fund",  "Large Blend",        0,  5_000,   6_300, "2020-04-12"),
    ("Vanguard Total Bond",    "VBTLX", "mutual_fund",  "Intermediate Core Bond", 0, 8_000, 7_850, "2020-07-01"),
    ("T. Rowe Price Growth",   "PRGFX", "mutual_fund",  "Large Growth",       0,  7_500,   9_900, "2019-11-15"),
    ("Schwab Total Market",    "SWTSX", "mutual_fund",  "Large Blend",        0,  6_000,   7_400, "2021-04-20"),
]

TARGET_ALLOCATIONS = [
    ("Technology",              18),
    ("Communication Services",   8),
    ("Consumer Cyclical",        8),
    ("Financial Services",       7),
    ("Healthcare",               7),
    ("Large Blend",             22),
    ("Large Growth",            10),
    ("Foreign Large Blend",      5),
    ("Treasury",                 8),
    ("Intermediate Core Bond",   5),
    ("Short-Term Bond",          2),
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

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)

    # Migrate older databases created by previous versions of this script/app.
    holding_cols = [row[1] for row in conn.execute("PRAGMA table_info(holdings)")]
    if "category" not in holding_cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN category TEXT NOT NULL DEFAULT ''")

    allocation_cols = [row[1] for row in conn.execute("PRAGMA table_info(target_allocations)")]
    if "asset_type" in allocation_cols and "category" not in allocation_cols:
        conn.execute("ALTER TABLE target_allocations RENAME COLUMN asset_type TO category")

    inserted = 0
    for name, ticker, asset_type, category, shares, cost_basis, current_value, purchase_date in HOLDINGS:
        exists = conn.execute(
            "SELECT 1 FROM holdings WHERE name = ? AND asset_type = ?", (name, asset_type)
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO holdings
                       (name, ticker, asset_type, category, shares, cost_basis, current_value,
                        purchase_date, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                (name, ticker, asset_type, category, shares, cost_basis, current_value,
                 purchase_date, now, now),
            )
            inserted += 1

    target_count = conn.execute("SELECT COUNT(*) FROM target_allocations").fetchone()[0]
    targets_inserted = 0
    if target_count == 0:
        for category, target_pct in TARGET_ALLOCATIONS:
            conn.execute(
                """INSERT INTO target_allocations (category, target_percentage)
                   VALUES (?, ?)""",
                (category, target_pct),
            )
            targets_inserted += 1

    conn.commit()
    conn.close()

    total = len(HOLDINGS)
    skipped = total - inserted
    print(f"Seeded {inserted} holding(s). {skipped} already existed — skipped.")
    print(f"Seeded {targets_inserted} target allocation(s). Existing target allocations are left untouched.")


if __name__ == "__main__":
    seed()

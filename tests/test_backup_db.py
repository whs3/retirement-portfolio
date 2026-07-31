"""Tests for the online-safe SQLite backup helper."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from backup_db import backup_database, main


def _make_db(path: Path, *, rows: int = 3) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany(
        "INSERT INTO items (name) VALUES (?)",
        [(f"row-{i}",) for i in range(rows)],
    )
    conn.commit()
    conn.close()


def test_backup_database_copies_data(tmp_path):
    src = tmp_path / "portfolio.db"
    dest_dir = tmp_path / "backups"
    _make_db(src, rows=5)

    dest = backup_database(src, dest_dir, keep=5, prefix="portfolio")
    assert dest.is_file()
    assert dest.parent == dest_dir

    conn = sqlite3.connect(str(dest))
    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    assert count == 5


def test_backup_prunes_old_files(tmp_path):
    src = tmp_path / "portfolio.db"
    dest_dir = tmp_path / "backups"
    _make_db(src)

    created = []
    for i in range(5):
        path = backup_database(src, dest_dir, keep=100, prefix="portfolio")
        # Force strictly increasing mtimes so prune order is deterministic
        os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
        created.append(path)

    # Re-run once more with keep=2 to trigger prune of the older five
    newest = backup_database(src, dest_dir, keep=2, prefix="portfolio")
    os.utime(newest, (1_700_000_000 + 10, 1_700_000_000 + 10))

    remaining = sorted(dest_dir.glob("portfolio-*.db"), key=lambda p: p.stat().st_mtime)
    assert len(remaining) == 2
    assert remaining[-1] == newest
    assert remaining[0] in created

def test_backup_cli_success(tmp_path, capsys):
    src = tmp_path / "portfolio.db"
    dest_dir = tmp_path / "out"
    _make_db(src)

    rc = main(["--db", str(src), "--dir", str(dest_dir), "--keep", "3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Backup written:" in out
    assert list(dest_dir.glob("portfolio-*.db"))


def test_backup_cli_missing_db(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "missing.db"), "--dir", str(tmp_path / "out")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Database not found" in err

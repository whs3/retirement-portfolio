#!/usr/bin/env python3
"""Online-safe SQLite backup for the retirement portfolio database.

Uses the SQLite backup API so it is safe while the app is running (including
WAL mode). By default writes timestamped copies under ``backups/`` and prunes
older files.

Examples:
    python backup_db.py
    python backup_db.py --db /path/to/portfolio.db --dir /var/backups/portfolio
    python backup_db.py --keep 30
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from portfolio.config import PROJECT_ROOT, load_dotenv, resolve_path


def backup_database(
    db_path: Path,
    backup_dir: Path,
    *,
    keep: int = 14,
    prefix: str = "portfolio",
) -> Path:
    """Copy *db_path* into *backup_dir* and prune old backups.

    Returns the path of the newly created backup file.
    """
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    # Include microseconds so rapid successive backups never collide
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    dest = backup_dir / f"{prefix}-{stamp}.db"
    if dest.exists():
        dest = backup_dir / f"{prefix}-{stamp}-{os.getpid()}.db"

    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")  # single-file backup artifact
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    if keep > 0:
        _prune_backups(backup_dir, prefix=prefix, keep=keep)

    return dest


def _prune_backups(backup_dir: Path, *, prefix: str, keep: int) -> None:
    """Keep the newest *keep* ``{prefix}-*.db`` files; delete the rest."""
    files = sorted(
        (
            p
            for p in backup_dir.iterdir()
            if p.is_file() and p.name.startswith(f"{prefix}-") and p.suffix == ".db"
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError as exc:
            print(f"warning: could not remove old backup {old}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Backup the retirement portfolio SQLite database (WAL-safe).",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("PORTFOLIO_DATABASE", "portfolio.db"),
        help="Source database path (default: PORTFOLIO_DATABASE or portfolio.db)",
    )
    parser.add_argument(
        "--dir",
        default=os.getenv("PORTFOLIO_BACKUP_DIR", str(PROJECT_ROOT / "backups")),
        help="Backup directory (default: PORTFOLIO_BACKUP_DIR or ./backups)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=int(os.getenv("PORTFOLIO_BACKUP_KEEP", "14")),
        help="Number of backups to retain (0 = keep all; default: 14)",
    )
    parser.add_argument(
        "--prefix",
        default="portfolio",
        help="Backup filename prefix (default: portfolio)",
    )
    args = parser.parse_args(argv)

    db_path = Path(resolve_path(args.db))
    backup_dir = Path(resolve_path(args.dir))

    try:
        dest = backup_database(db_path, backup_dir, keep=args.keep, prefix=args.prefix)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"error: SQLite backup failed: {exc}", file=sys.stderr)
        return 1

    size_kb = dest.stat().st_size / 1024
    print(f"Backup written: {dest} ({size_kb:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

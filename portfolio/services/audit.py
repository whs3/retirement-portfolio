"""Append-only audit log for holding mutations."""

import logging
import os
import re
import threading
from datetime import datetime, timedelta

from flask import current_app

_audit_logger = logging.getLogger("portfolio.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False

_app_logger = logging.getLogger("portfolio.app")

_handler_path: str | None = None

# How many days of entries the live log (and /api/audit) keep. Anything
# older is moved into monthly files under an audit_archive/ directory next
# to the log, so the file the API parses on every request stays small.
RETENTION_DAYS = 7

_ARCHIVE_LOCK = threading.Lock()
_LINE_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} \|")


def init_audit_log(log_path: str) -> None:
    """Attach a file handler for the audit log (idempotent per path)."""
    global _handler_path
    if _handler_path == log_path:
        return
    # Replace handlers if path changes (e.g. tests)
    for h in list(_audit_logger.handlers):
        _audit_logger.removeHandler(h)
        h.close()
    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _audit_logger.addHandler(handler)
    _handler_path = log_path


def audit(action: str, ticker: str, name: str, **fields):
    """Write one line to the audit log.

    Example output:
        2026-02-21 14:30:00 | ADD    | AAPL | Apple Inc. | current_value=$11200.00 cost_basis=$7500.00
    """
    # Ensure handler is attached when called under an app context
    if _handler_path is None:
        try:
            init_audit_log(current_app.config["AUDIT_LOG"])
        except RuntimeError:
            pass

    ticker_col = (ticker or "—").ljust(6)
    kv = "  ".join(
        f"{k}=${v:.2f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in fields.items()
    )
    _audit_logger.info("%-6s | %s | %s | %s", action, ticker_col, name, kv)


def get_app_logger() -> logging.Logger:
    return _app_logger


def archive_old_entries(log_path: str, retention_days: int = RETENTION_DAYS) -> int:
    """Move lines older than *retention_days* out of the live log into
    monthly files under an ``audit_archive/`` directory next to it.

    Keeps the file ``/api/audit`` parses on every request small instead of
    growing forever. Returns the number of lines archived.
    """
    if not os.path.isfile(log_path):
        return 0

    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")

    with _ARCHIVE_LOCK:
        with open(log_path, "r") as f:
            lines = f.readlines()

        keep = []
        by_month: dict[str, list[str]] = {}
        for line in lines:
            match = _LINE_TIMESTAMP_RE.match(line)
            line_date = match.group(1) if match else None
            if line_date is None or line_date >= cutoff:
                keep.append(line)
            else:
                by_month.setdefault(line_date[:7], []).append(line)

        if not by_month:
            return 0

        archive_dir = os.path.join(os.path.dirname(os.path.abspath(log_path)), "audit_archive")
        os.makedirs(archive_dir, exist_ok=True)
        for month, month_lines in by_month.items():
            archive_path = os.path.join(archive_dir, f"portfolio_audit-{month}.log")
            with open(archive_path, "a") as f:
                f.writelines(month_lines)

        # The live FileHandler holds this path open in append mode. Close it
        # before rewriting the file and reopen after, so it doesn't keep
        # writing into what would otherwise become a stale file descriptor.
        global _handler_path
        was_attached = _handler_path == log_path
        if was_attached:
            for h in list(_audit_logger.handlers):
                _audit_logger.removeHandler(h)
                h.close()
            _handler_path = None

        with open(log_path, "w") as f:
            f.writelines(keep)

        if was_attached:
            init_audit_log(log_path)

        return sum(len(v) for v in by_month.values())


def start_audit_archiver(app) -> None:
    """Daemon thread that periodically archives old audit-log entries.

    Skipped in tests and in the debug reloader's parent process, matching
    the price-refresh scheduler's guards.
    """
    if app.config.get("TESTING"):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return
    if app.extensions.get("audit_archive_thread"):
        return

    stop = threading.Event()
    log_path = app.config["AUDIT_LOG"]

    def loop() -> None:
        # The startup call in create_app() already archived once; wait a
        # full day before checking again.
        while not stop.wait(24 * 60 * 60):
            try:
                archived = archive_old_entries(log_path)
                if archived:
                    _app_logger.info("audit log archive: moved %d old line(s)", archived)
            except Exception:
                _app_logger.exception("audit log archive failed")

    thread = threading.Thread(target=loop, name="audit-archive", daemon=True)
    app.extensions["audit_archive_stop"] = stop
    app.extensions["audit_archive_thread"] = thread
    thread.start()

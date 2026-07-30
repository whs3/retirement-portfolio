"""Append-only audit log for holding mutations."""

import logging

from flask import current_app

_audit_logger = logging.getLogger("portfolio.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False

_app_logger = logging.getLogger("portfolio.app")

_handler_path: str | None = None


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

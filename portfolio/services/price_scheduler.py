"""Background loop that refreshes holding prices on a configurable interval."""

from __future__ import annotations

import logging
import os
import threading
import time

from portfolio.services.prices import refresh_all_prices
from portfolio.services.settings import get_price_refresh_minutes

log = logging.getLogger("portfolio.app")

_POLL_SECONDS = 5
_STARTUP_DELAY_SECONDS = 15


def start_price_refresh_scheduler(app) -> None:
    """Start a daemon thread that auto-refreshes prices.

    Skipped in tests, when explicitly disabled, and in the Flask debug
    reloader's parent process so only one worker actually polls yfinance.
    """
    if app.config.get("TESTING"):
        return
    if app.config.get("PRICE_REFRESH_SCHEDULER") is False:
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return
    if app.extensions.get("price_refresh_thread"):
        return

    stop = threading.Event()

    def loop() -> None:
        if stop.wait(_STARTUP_DELAY_SECONDS):
            return
        last_run = 0.0
        while not stop.is_set():
            try:
                with app.app_context():
                    minutes = get_price_refresh_minutes()
                if minutes > 0:
                    elapsed = time.monotonic() - last_run
                    due = last_run == 0.0 or elapsed >= minutes * 60
                    if due:
                        with app.app_context():
                            result = refresh_all_prices()
                        last_run = time.monotonic()
                        log.info(
                            "auto price refresh: updated=%s skipped=%s errors=%s",
                            len(result["updated"]),
                            len(result["skipped"]),
                            len(result["errors"]),
                        )
            except Exception:
                log.exception("auto price refresh failed")
                last_run = time.monotonic()
            if stop.wait(_POLL_SECONDS):
                return

    thread = threading.Thread(target=loop, name="price-refresh", daemon=True)
    app.extensions["price_refresh_stop"] = stop
    app.extensions["price_refresh_thread"] = thread
    thread.start()

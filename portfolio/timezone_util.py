"""Server IANA timezone detection for template timestamps and snapshot dates."""

import os
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo


def detect_iana_timezone() -> str:
    tz = os.environ.get("TZ", "")
    if tz:
        return tz
    try:
        return pathlib.Path("/etc/timezone").read_text().strip()
    except OSError:
        pass
    p = pathlib.Path("/etc/localtime")
    if p.is_symlink():
        target = str(p.resolve())
        idx = target.find("zoneinfo/")
        if idx != -1:
            return target[idx + 9:]
    return "UTC"


SERVER_TIMEZONE = detect_iana_timezone()


def server_zone() -> ZoneInfo:
    """IANA zone for the machine running the app. Falls back to UTC."""
    try:
        return ZoneInfo(SERVER_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def now_local() -> datetime:
    """Current time in the server's timezone."""
    return datetime.now(server_zone())


def today_iso() -> str:
    """Today's calendar date (YYYY-MM-DD) in the server's timezone."""
    return now_local().date().isoformat()


def now_iso() -> str:
    """Timezone-aware timestamp, seconds precision, for stored created_at values."""
    return now_local().replace(microsecond=0).isoformat()

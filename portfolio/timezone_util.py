"""Server IANA timezone detection for template timestamps."""

import os
import pathlib


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

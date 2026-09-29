"""Input validation helpers used at API boundaries."""

import math
import re

# Ticker symbols allowed on price/lookup/sell-all routes.
VALID_TICKER = re.compile(r"^[\w.\-\^]{1,20}$")

# At or below this magnitude, a summed dollar value is treated as fully sold /
# rounding dust rather than a real position (dashboard breakdowns hide it).
NEGLIGIBLE_VALUE = 0.01


def is_significant_value(value: float, threshold: float = NEGLIGIBLE_VALUE) -> bool:
    """Return True if *value* is a real position after cent rounding.

    Compares on ``round(value, 2)`` so float residuals like ``-0.01000000003``
    (displayed as -$0.01) are treated as dust, same as an exact ``±0.01``.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    if math.isnan(n) or math.isinf(n):
        return False
    return abs(round(n, 2)) > threshold


def parse_positive_float(value, field_name: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number") from None
    if math.isnan(n) or math.isinf(n):
        raise ValueError(f"{field_name} is not a valid number")
    if n < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return n


def parse_float(value, field_name: str) -> float:
    """Like parse_positive_float but allows negative values (for sell transactions)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number") from None
    if math.isnan(n) or math.isinf(n):
        raise ValueError(f"{field_name} is not a valid number")
    return n


def sanitize_for_json(obj):
    """Recursively replace NaN/Infinity floats with None.

    Python's ``json.dumps``/Flask's ``jsonify`` serialize ``float('nan')`` and
    ``float('inf')`` as bare ``NaN``/``Infinity`` tokens, which are not valid
    JSON and make ``JSON.parse`` in the browser fail. Data pulled from
    yfinance/pandas can carry NaNs (e.g. sparse history rows), so any route
    building a response from that data should sanitize it before ``jsonify``.
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

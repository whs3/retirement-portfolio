"""Input validation helpers used at API boundaries."""

import math
import re

# Ticker symbols allowed on price/lookup/sell-all routes.
VALID_TICKER = re.compile(r"^[\w.\-\^]{1,20}$")

# At or below this magnitude, a summed dollar value is treated as fully sold /
# rounding dust rather than a real position (dashboard breakdowns hide it).
NEGLIGIBLE_VALUE = 0.01


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

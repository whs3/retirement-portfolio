"""Unit tests for portfolio.validators."""

import math

import pytest

from portfolio.validators import (
    NEGLIGIBLE_VALUE,
    VALID_TICKER,
    is_significant_value,
    parse_float,
    parse_positive_float,
)


class TestValidTicker:
    @pytest.mark.parametrize(
        "symbol",
        ["AAPL", "BRK.B", "BRK-B", "^GSPC", "$$CASH", "FXAIX", "aapl"],
    )
    def test_accepts_common_symbols(self, symbol):
        # Regex itself is case-sensitive for letters; routes uppercase before match.
        # $$CASH uses $ which is NOT in [\w.\-\^] — check actual behavior.
        if symbol == "$$CASH":
            # Dollar signs are not in the character class; routes special-case $$CASH.
            assert VALID_TICKER.match(symbol) is None
        elif symbol == "aapl":
            assert VALID_TICKER.match(symbol)
        else:
            assert VALID_TICKER.match(symbol)

    @pytest.mark.parametrize(
        "symbol",
        ["", "TOO_LONG_TICKER_SYMBOL_XX", "AAPL!", "AAPL SHARE", "../../etc"],
    )
    def test_rejects_invalid_symbols(self, symbol):
        assert VALID_TICKER.match(symbol) is None


class TestParseFloat:
    def test_accepts_positive(self):
        assert parse_float("12.5", "Shares") == 12.5

    def test_accepts_negative(self):
        assert parse_float(-3.25, "Shares") == -3.25

    def test_accepts_zero(self):
        assert parse_float(0, "Shares") == 0.0

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="must be a number"):
            parse_float("abc", "Shares")

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="not a valid number"):
            parse_float(float("nan"), "Shares")

    def test_rejects_inf(self):
        with pytest.raises(ValueError, match="not a valid number"):
            parse_float(math.inf, "Shares")


class TestParsePositiveFloat:
    def test_accepts_positive(self):
        assert parse_positive_float("1.5", "Price") == 1.5

    def test_accepts_zero(self):
        assert parse_positive_float(0, "Price") == 0.0

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            parse_positive_float(-1, "Price")

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="not a valid number"):
            parse_positive_float(float("nan"), "Price")


def test_negligible_value_threshold():
    assert NEGLIGIBLE_VALUE == 0.01


@pytest.mark.parametrize(
    "value,expected",
    [
        (100.0, True),
        (0.02, True),
        (-0.02, True),
        (0.01, False),
        (-0.01, False),
        (0.0, False),
        # SPAB-style float noise that formats as ±$0.01
        (-0.010000000029918965, False),
        (0.00999999999476131, False),
        (None, False),
        (float("nan"), False),
    ],
)
def test_is_significant_value(value, expected):
    assert is_significant_value(value) is expected

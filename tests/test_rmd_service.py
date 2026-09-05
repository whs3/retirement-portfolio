"""Unit tests for RMD estimation (portfolio.services.rmd)."""

from datetime import date

import pytest

from portfolio.services.rmd import (
    UNIFORM_LIFETIME_TABLE,
    calculate_age,
    calculate_rmd,
    rmd_start_age,
)


@pytest.mark.parametrize(
    "birth_year, expected",
    [
        (1945, 72),
        (1950, 72),
        (1951, 73),
        (1959, 73),
        (1960, 75),
        (1970, 75),
    ],
)
def test_rmd_start_age(birth_year, expected):
    assert rmd_start_age(birth_year) == expected


def test_calculate_age_before_birthday_this_year():
    assert calculate_age(date(1960, 6, 15), date(2026, 6, 14)) == 65


def test_calculate_age_on_or_after_birthday_this_year():
    assert calculate_age(date(1960, 6, 15), date(2026, 6, 15)) == 66
    assert calculate_age(date(1960, 6, 15), date(2026, 12, 31)) == 66


def test_not_yet_required_below_start_age():
    # Born 1960 -> RMD age 75; turns 70 on this as_of date.
    result = calculate_rmd(date(1956, 3, 1), 100_000, as_of=date(2026, 3, 1))
    assert result["age"] == 70
    assert result["rmd_start_age"] == 73
    assert result["required"] is False
    assert result["years_until_required"] == 3
    assert result["rmd_amount"] == 0.0
    assert result["distribution_period"] is None


def test_required_at_exact_start_age():
    # Born 1951 -> RMD age 73; turns exactly 73 on this as_of date.
    result = calculate_rmd(date(1953, 5, 1), 730_000, as_of=date(2026, 5, 1))
    assert result["age"] == 73
    assert result["required"] is True
    assert result["distribution_period"] == UNIFORM_LIFETIME_TABLE[73]
    assert result["rmd_amount"] == round(730_000 / UNIFORM_LIFETIME_TABLE[73], 2)


def test_zero_balance_gives_zero_rmd_even_if_required():
    result = calculate_rmd(date(1945, 1, 1), 0, as_of=date(2026, 1, 1))
    assert result["required"] is True
    assert result["rmd_amount"] == 0.0
    assert result["distribution_period"] is None


def test_age_beyond_table_clamps_to_max():
    # Table tops out at 120; a very old owner should use the age-120 factor.
    result = calculate_rmd(date(1900, 1, 1), 50_000, as_of=date(2026, 1, 1))
    assert result["age"] > 120
    assert result["distribution_period"] == UNIFORM_LIFETIME_TABLE[120]

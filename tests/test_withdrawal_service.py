"""Unit tests for withdrawal projection (portfolio.services.withdrawal)."""

from datetime import date

from portfolio.services.withdrawal import project_withdrawals


def test_zero_withdrawal_only_grows():
    result = project_withdrawals(100_000, 0, 5, 2, 3)
    assert result["depletion_year"] is None
    assert result["rows"][0]["withdrawal"] == 0.0
    assert result["rows"][0]["end_balance"] == 105_000.0
    assert result["rows"][1]["end_balance"] == round(105_000 * 1.05, 2)


def test_never_depletes_when_return_exceeds_withdrawal():
    result = project_withdrawals(1_000_000, 4, 6, 3, 30)
    assert result["depletion_year"] is None
    assert result["final_balance"] > result["starting_balance"]
    assert len(result["rows"]) == 30


def test_depletes_when_withdrawal_exceeds_return():
    result = project_withdrawals(100_000, 10, 2, 3, 40)
    assert result["depletion_year"] is not None
    depleted_row = result["rows"][result["depletion_year"] - 1]
    assert depleted_row["end_balance"] == 0.0
    # Every year after depletion should stay at zero.
    for row in result["rows"][result["depletion_year"]:]:
        assert row["start_balance"] == 0.0
        assert row["withdrawal"] == 0.0
        assert row["end_balance"] == 0.0


def test_first_year_withdrawal_matches_rate_times_starting_balance():
    result = project_withdrawals(200_000, 4, 6, 3, 10)
    assert result["first_year_withdrawal"] == 8_000.0
    assert result["rows"][0]["withdrawal"] == 8_000.0


def test_withdrawal_grows_with_inflation_each_year():
    result = project_withdrawals(500_000, 4, 6, 3, 3)
    w1 = result["rows"][0]["withdrawal"]
    w2 = result["rows"][1]["withdrawal"]
    assert w2 == round(w1 * 1.03, 2)


def test_calendar_year_labels_start_next_year():
    result = project_withdrawals(100_000, 4, 6, 3, 2)
    this_year = date.today().year
    assert result["rows"][0]["calendar_year"] == this_year + 1
    assert result["rows"][1]["calendar_year"] == this_year + 2


def test_zero_starting_balance():
    result = project_withdrawals(0, 4, 6, 3, 5)
    assert result["depletion_year"] is None
    assert all(row["end_balance"] == 0.0 for row in result["rows"])

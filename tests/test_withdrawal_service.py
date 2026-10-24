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


def test_rmd_floor_raises_the_withdrawal_and_taxes_by_account():
    result = project_withdrawals(
        200_000, 4, 6, 0, 2,
        rmd_by_calendar_year={2027: 20_000, 2028: 5_000},
        buckets={"pretax": 100_000, "taxable": 50_000, "roth": 50_000},
        ordinary_tax_pct=22,
        gains_tax_pct=15,
        as_of=date(2026, 6, 1),
    )
    first = result["rows"][0]
    assert first["calendar_year"] == 2027
    assert first["planned_withdrawal"] == 8_000
    assert first["rmd"] == 20_000
    assert first["withdrawal"] == 20_000
    assert first["sources"] == {"pretax": 20_000, "taxable": 0, "roth": 0}
    assert first["tax"] == 4_400
    assert first["spendable"] == 15_600
    assert first["end_balance"] == 190_800

    second = result["rows"][1]
    assert second["rmd"] == 5_000
    assert second["withdrawal"] == 8_000
    assert second["sources"]["pretax"] == 5_000
    assert second["sources"]["taxable"] == 3_000
    assert second["sources"]["roth"] == 0
    assert second["tax"] == 1_550
    assert second["spendable"] == 6_450


def test_roth_withdrawal_is_untaxed():
    result = project_withdrawals(
        100_000, 4, 0, 0, 1,
        buckets={"pretax": 0, "taxable": 0, "roth": 100_000},
        ordinary_tax_pct=22,
        gains_tax_pct=15,
        as_of=date(2026, 1, 1),
    )
    row = result["rows"][0]
    assert row["sources"]["roth"] == 4_000
    assert row["tax"] == 0
    assert row["spendable"] == 4_000


def test_rates_alone_do_not_tax_a_projection_without_account_balances():
    result = project_withdrawals(100_000, 4, 0, 0, 1, ordinary_tax_pct=22, gains_tax_pct=15)
    assert result["rows"][0]["withdrawal"] == 4_000
    assert result["rows"][0]["tax"] == 0
    assert result["rows"][0]["spendable"] == 4_000

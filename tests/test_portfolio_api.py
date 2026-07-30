"""API tests for summary, allocations, and rebalance."""


def test_summary_totals(client, seed_holdings):
    r = client.get("/api/portfolio/summary")
    assert r.status_code == 200
    data = r.get_json()

    # Seeded: 2000 + 2500 + 5100 + 1000 + 10 + (-9.995) = 10600.005
    assert abs(data["total_value"] - 10600.005) < 0.01
    assert data["count"] == 6
    assert "gain_loss" in data
    assert "allocation" in data
    assert "category_allocation" in data
    assert "owner_allocation" in data
    assert "account_type_allocation" in data


def test_summary_filters_negligible_category_dust(client, seed_holdings):
    """DUST nets to ~0.005 which is below NEGLIGIBLE_VALUE for category display.

    Category Technology includes AAPL (2000) + DUST net (~0.005) so it still shows.
    Owner/type breakdowns with only dust would be hidden — verify asset types present.
    """
    data = client.get("/api/portfolio/summary").get_json()
    types = {a["asset_type"] for a in data["allocation"]}
    assert "stock" in types
    assert "etf" in types
    assert "bond" in types
    assert "cash" in types

    # No allocation entry should have abs(value) <= 0.01
    for a in data["allocation"]:
        assert abs(a["value"]) > 0.01
    for a in data["category_allocation"]:
        assert abs(a["value"]) > 0.01


def test_summary_owner_breakdown(client, seed_holdings):
    data = client.get("/api/portfolio/summary").get_json()
    owners = {o["owner"]: o["value"] for o in data["owner_allocation"]}
    assert owners["Bill"] == 2000 + 1000 + 0.005  # AAPL + cash + dust net
    assert abs(owners["Bill"] - 3000.005) < 0.01
    assert owners["Akiko"] == 2500
    assert owners["Joint"] == 5100


def test_get_allocations(client, seed_holdings):
    r = client.get("/api/allocations")
    assert r.status_code == 200
    data = r.get_json()
    by_cat = {a["category"]: a["target_percentage"] for a in data}
    assert by_cat["Technology"] == 40
    assert by_cat["Large Blend"] == 30
    # Categories present only in holdings should appear with 0 if not targeted —
    # Cash/Treasury are targeted in seed.


def test_update_allocations_must_sum_to_100(client, seed_holdings):
    r = client.put(
        "/api/allocations",
        json=[
            {"category": "Technology", "target_percentage": 50},
            {"category": "Large Blend", "target_percentage": 30},
        ],
    )
    assert r.status_code == 400
    assert "must sum to 100%" in r.get_json()["error"]


def test_update_allocations_success(client, seed_holdings):
    payload = [
        {"category": "Technology", "target_percentage": 50},
        {"category": "Large Blend", "target_percentage": 25},
        {"category": "Treasury", "target_percentage": 15},
        {"category": "Cash", "target_percentage": 10},
    ]
    r = client.put("/api/allocations", json=payload)
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    by_cat = {
        a["category"]: a["target_percentage"]
        for a in client.get("/api/allocations").get_json()
    }
    assert by_cat["Technology"] == 50
    assert by_cat["Cash"] == 10


def test_rebalance_actions(client, seed_holdings):
    """With targets set, recommendations should classify Buy/Sell/Hold."""
    r = client.get("/api/rebalance")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_value"] > 0
    recs = {row["category"]: row for row in data["recommendations"]}

    # Technology current ≈ 2000.005 / 10600 ≈ 18.9% vs target 40% → Buy
    assert recs["Technology"]["action"] == "Buy"
    assert recs["Technology"]["difference"] > 1

    # Treasury current 5100 / 10600 ≈ 48% vs target 20% → Sell
    assert recs["Treasury"]["action"] == "Sell"
    assert recs["Treasury"]["difference"] < -1

    # Each recommendation has expected fields
    for row in data["recommendations"]:
        assert set(row.keys()) >= {
            "category",
            "current_value",
            "current_pct",
            "target_pct",
            "target_value",
            "difference",
            "action",
        }


def test_rebalance_hold_when_close(client, insert_holding, app):
    """When current matches target within $1, action is Hold."""
    # Single category portfolio with 100% target
    insert_holding(
        name="Only",
        ticker="AAA",
        asset_type="stock",
        category="Technology",
        shares=1,
        cost_basis=100,
        current_value=100,
    )
    client.put(
        "/api/allocations",
        json=[{"category": "Technology", "target_percentage": 100}],
    )
    recs = client.get("/api/rebalance").get_json()["recommendations"]
    tech = next(r for r in recs if r["category"] == "Technology")
    assert tech["action"] == "Hold"
    assert abs(tech["difference"]) <= 1

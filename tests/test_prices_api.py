"""Price API tests with yfinance mocked (no network)."""

from unittest.mock import MagicMock, patch


def test_get_price_invalid_ticker(client):
    r = client.get("/api/price/BAD TICKER!")
    assert r.status_code == 400
    assert "Invalid ticker" in r.get_json()["error"]


def test_get_price_cash_special(client):
    r = client.get("/api/price/$$CASH")
    assert r.status_code == 200
    data = r.get_json()
    assert data["price"] == 1.0
    assert data["category"] == "Cash"


def test_get_price_success(client):
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "regularMarketPrice": 150.25,
        "longName": "Apple Inc.",
        "sector": "Technology",
    }
    mock_ticker.fast_info.last_price = 149.0

    with patch("portfolio.routes.prices.yf.Ticker", return_value=mock_ticker):
        r = client.get("/api/price/AAPL")

    assert r.status_code == 200
    data = r.get_json()
    assert data["ticker"] == "AAPL"
    assert data["price"] == 150.25
    assert data["name"] == "Apple Inc."
    assert data["category"] == "Technology"


def test_get_price_unavailable(client):
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_ticker.fast_info.last_price = None

    with patch("portfolio.routes.prices.yf.Ticker", return_value=mock_ticker):
        r = client.get("/api/price/ZZZZ")

    assert r.status_code == 404


def test_refresh_prices(client, seed_holdings):
    def fake_ticker(symbol):
        t = MagicMock()
        prices = {"AAPL": 200.0, "VOO": 500.0, "SPAXX": 1.0, "DUST": 1.0}
        price = prices.get(symbol.upper(), 10.0)
        t.info = {
            "regularMarketPrice": price,
            "category": "Large Blend",
            "sector": "Technology",
        }
        t.fast_info.last_price = price
        return t

    with patch("portfolio.services.prices.yf.Ticker", side_effect=fake_ticker) as mock_ticker:
        r = client.post("/api/holdings/refresh-prices")

    assert r.status_code == 200
    body = r.get_json()
    assert "updated" in body
    assert isinstance(body["updated"], list)
    assert len(body["updated"]) >= 1
    # One Yahoo lookup per symbol, including the two DUST lots.
    fetched = [c.args[0] for c in mock_ticker.call_args_list]
    assert len(fetched) == len(set(fetched))
    assert set(fetched) == {"AAPL", "VOO", "SPAXX", "DUST"}

    # AAPL: 10 shares * 200 = 2000. A category the user already set is kept.
    aapl_rows = [h for h in client.get("/api/holdings").get_json() if h["ticker"] == "AAPL"]
    assert aapl_rows[0]["current_value"] == 2000.0
    assert aapl_rows[0]["category"] == "Technology"


def test_refresh_prices_fills_only_blank_category(client, insert_holding):
    insert_holding(
        ticker="MSFT", name="Microsoft", category="", shares=2,
        current_value=100, cost_basis=80, owner="Bill", account_type="IRA",
    )
    insert_holding(
        ticker="MSFT", name="Microsoft", category="Custom Bucket", shares=1,
        current_value=50, cost_basis=40, owner="Akiko", account_type="Broker",
    )

    def fake_ticker(symbol):
        t = MagicMock()
        t.info = {"regularMarketPrice": 50.0, "category": "Large Blend"}
        t.fast_info.last_price = 50.0
        return t

    with patch("portfolio.services.prices.yf.Ticker", side_effect=fake_ticker) as mock_ticker:
        r = client.post("/api/holdings/refresh-prices")

    assert r.status_code == 200
    assert mock_ticker.call_count == 1
    rows = {
        h["owner"]: h
        for h in client.get("/api/holdings").get_json()
        if h["ticker"] == "MSFT"
    }
    assert rows["Bill"]["category"] == "Large Blend"
    assert rows["Bill"]["current_value"] == 100.0
    assert rows["Akiko"]["category"] == "Custom Bucket"
    assert rows["Akiko"]["current_value"] == 50.0

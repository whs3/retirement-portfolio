"""CSV export API tests."""


def test_export_csv_empty(client):
    r = client.get("/api/export/csv")
    assert r.status_code == 200
    assert "text/csv" in r.content_type
    text = r.data.decode("utf-8")
    assert "Name" in text
    assert "Ticker" in text
    # header only
    lines = [ln for ln in text.strip().splitlines() if ln]
    assert len(lines) == 1


def test_export_csv_with_holdings(client, seed_holdings):
    r = client.get("/api/export/csv")
    assert r.status_code == 200
    text = r.data.decode("utf-8")
    assert "AAPL" in text
    assert "Apple Inc." in text
    assert "VOO" in text
    # Content-Disposition attachment
    assert "attachment" in r.headers.get("Content-Disposition", "").lower()

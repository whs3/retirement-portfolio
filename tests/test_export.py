"""CSV export/import API tests."""

import csv
import io

from portfolio.db import get_db
from portfolio.routes.export import CSV_HEADERS


def _csv_bytes(rows):
    """Build CSV bytes with the app's export headers and given data rows (lists)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADERS)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _upload(client, data_bytes, filename="import.csv"):
    return client.post(
        "/api/import/csv",
        data={"file": (io.BytesIO(data_bytes), filename)},
        content_type="multipart/form-data",
    )


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


def test_import_csv_valid_rows(client, app):
    data = _csv_bytes([
        ["Apple Inc.", "AAPL", "Stock", "Bill", "IRA", "10",
         "1000.00", "1500.00", "500.00", "50.00", "2024-01-01", ""],
        ["Cash Reserve", "$$CASH", "Cash", "Bill", "Broker", "250",
         "250.00", "250.00", "0.00", "0.00", "2024-01-01", "money market"],
    ])
    res = _upload(client, data)
    assert res.status_code == 201
    body = res.get_json()
    assert body["success"] is True
    assert body["imported"] == 2

    with app.app_context():
        rows = get_db().execute("SELECT * FROM holdings ORDER BY ticker").fetchall()
    assert len(rows) == 2
    cash = next(r for r in rows if r["ticker"] == "$$CASH")
    assert cash["category"] == "Cash"
    assert cash["current_value"] == 250  # forced to match shares
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["asset_type"] == "stock"
    assert aapl["shares"] == 10
    assert aapl["cost_basis"] == 1000


def test_import_csv_header_mismatch(client, app):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Ticker", "Shares"])
    writer.writerow(["Apple Inc.", "AAPL", "10"])

    res = _upload(client, buf.getvalue().encode("utf-8"))
    assert res.status_code == 400
    assert "headers" in res.get_json()["error"].lower()

    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) AS c FROM holdings").fetchone()["c"]
    assert count == 0


def test_import_csv_bad_row_is_all_or_nothing(client, app):
    data = _csv_bytes([
        ["Apple Inc.", "AAPL", "Stock", "Bill", "IRA", "10",
         "1000.00", "1500.00", "500.00", "50.00", "2024-01-01", ""],
        ["Bad Row", "BAD", "Stock", "Bill", "IRA", "not-a-number",
         "100.00", "100.00", "0.00", "0.00", "2024-01-01", ""],
    ])
    res = _upload(client, data)
    assert res.status_code == 400
    body = res.get_json()
    assert body["row_errors"] == [{"row": 3, "error": "Shares must be a number"}]

    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) AS c FROM holdings").fetchone()["c"]
    assert count == 0  # the valid AAPL row was NOT imported either


def test_import_csv_no_file(client):
    res = client.post("/api/import/csv", data={}, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "file" in res.get_json()["error"].lower()


def test_import_csv_round_trip(client, app, seed_holdings):
    export_res = client.get("/api/export/csv")
    csv_bytes = export_res.data

    with app.app_context():
        before = get_db().execute("SELECT COUNT(*) AS c FROM holdings").fetchone()["c"]

    import_res = _upload(client, csv_bytes)
    assert import_res.status_code == 201
    assert import_res.get_json()["imported"] == before

    with app.app_context():
        db = get_db()
        after = db.execute("SELECT COUNT(*) AS c FROM holdings").fetchone()["c"]
        assert after == before * 2
        aapl_rows = db.execute(
            "SELECT * FROM holdings WHERE ticker = 'AAPL'"
        ).fetchall()
        assert len(aapl_rows) == 2
        assert {round(r["shares"], 2) for r in aapl_rows} == {10.0}
        assert {round(r["current_value"], 2) for r in aapl_rows} == {2000.0}

"""External deposits and withdrawals.

A positive amount is money (or securities) entering the portfolio. A negative
amount is money leaving. Investment gain for a stretch of snapshots is the
change in market value minus the cash flows inside that stretch, so adding
cash is not reported as a return.

Holding adds, share-count edits, deletes, sell-all, and CSV imports record a
flow automatically. The amount is the value that entered or left, not the
change in cost basis. Price refreshes and cost-basis-only edits do not. An
edit made the same day a holding was added or imported revises that entry's
flow instead, so fixing a typo does not leave a phantom deposit behind.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from portfolio.timezone_util import now_iso, now_local
from portfolio.validators import NEGLIGIBLE_VALUE, VALID_TICKER, is_significant_value, parse_float

SOURCE_MANUAL = "manual"
SOURCE_HOLDING_ADD = "holding_add"
SOURCE_HOLDING_EDIT = "holding_edit"
SOURCE_HOLDING_DELETE = "holding_delete"
SOURCE_SELL_ALL = "sell_all"
SOURCE_IMPORT = "import"

_SHARE_EPS = 1e-8
_NOTE_LIMIT = 200
_LABEL_LIMIT = 40


def external_flow_from_share_change(
    old_shares: float,
    old_value: float,
    new_shares: float,
    new_value: float,
) -> float:
    """Dollars that entered or left because the share count changed.

    The same share count is a price or cost-basis edit, and the flow is zero.
    Added shares are a deposit at the new price (new value / new shares).
    Removed shares are a withdrawal of those shares at that same new price.
    Closing the position (new shares are zero) treats the whole value change
    as external, because nothing remains to have earned a return on this edit.
    """
    old_shares = float(old_shares or 0)
    new_shares = float(new_shares or 0)
    old_value = float(old_value or 0)
    new_value = float(new_value or 0)
    if abs(new_shares - old_shares) <= _SHARE_EPS:
        return 0.0
    if abs(new_shares) <= _SHARE_EPS:
        return round(new_value - old_value, 2)
    price = new_value / new_shares
    return round((new_shares - old_shares) * price, 2)


def insert_cash_flow(
    db,
    *,
    flow_date: str,
    amount: float,
    owner: str = "",
    account_type: str = "",
    ticker: str = "",
    note: str = "",
    source: str = SOURCE_MANUAL,
    holding_id: int | None = None,
) -> int | None:
    """Insert one flow on ``db`` without committing. Dust amounts are skipped."""
    amount = round(float(amount), 2)
    if not is_significant_value(amount):
        return None
    cur = db.execute(
        """INSERT INTO cash_flows
               (flow_date, amount, owner, account_type, ticker, note, source,
                holding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            flow_date,
            amount,
            owner or "",
            account_type or "",
            ticker or "",
            note or "",
            source,
            holding_id,
            now_iso(),
        ),
    )
    return cur.lastrowid


def revise_same_day_add_flow(db, holding_id: int, flow_date: str, new_value: float) -> bool:
    """Re-price the add/import flow when its holding is edited the day it was entered.

    An edit on the entry day is treated as correcting the entry (for example,
    a sign typo), so the original flow becomes the holding's new value. The
    share-change rule would record nothing for a value-only edit, and a later
    delete would then offset the corrected value instead of the original one.
    Returns True when a flow was revised (or removed because it became dust),
    in which case the caller should not record a separate edit flow.
    Does not commit.
    """
    row = db.execute(
        """SELECT id FROM cash_flows
           WHERE holding_id = ? AND flow_date = ? AND source IN (?, ?)
           ORDER BY id DESC LIMIT 1""",
        (holding_id, flow_date, SOURCE_HOLDING_ADD, SOURCE_IMPORT),
    ).fetchone()
    if row is None:
        return False
    amount = round(float(new_value or 0), 2)
    if is_significant_value(amount):
        db.execute("UPDATE cash_flows SET amount = ? WHERE id = ?", (amount, row["id"]))
    else:
        db.execute("DELETE FROM cash_flows WHERE id = ?", (row["id"],))
    return True


def list_cash_flows(db, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Flows in ``[start_date, end_date]``, ordered by date then id."""
    sql = "SELECT * FROM cash_flows"
    params: list[str] = []
    clauses = []
    if start_date is not None:
        clauses.append("flow_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("flow_date <= ?")
        params.append(end_date)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY flow_date, id"
    return [_as_dict(row) for row in db.execute(sql, params).fetchall()]


def get_cash_flow(db, flow_id: int) -> dict | None:
    row = db.execute("SELECT * FROM cash_flows WHERE id = ?", (flow_id,)).fetchone()
    return _as_dict(row) if row else None


def delete_cash_flow(db, flow_id: int) -> dict | None:
    """Delete one flow and commit. Returns the deleted row, or None."""
    existing = get_cash_flow(db, flow_id)
    if existing is None:
        return None
    db.execute("DELETE FROM cash_flows WHERE id = ?", (flow_id,))
    db.commit()
    return existing


def parse_manual_flow(data: dict) -> dict:
    """Validate a user-entered flow. Raises ValueError with a message."""
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    flow_date = _parse_flow_date(data.get("flow_date"))
    amount = _parse_flow_amount(data.get("amount"))
    owner = _clip(data.get("owner"), _LABEL_LIMIT, "Owner")
    account_type = _clip(data.get("account_type"), _LABEL_LIMIT, "Account type")
    ticker = _parse_ticker(data.get("ticker"))
    note = _clip(data.get("note"), _NOTE_LIMIT, "Note")
    return {
        "flow_date": flow_date,
        "amount": amount,
        "owner": owner,
        "account_type": account_type,
        "ticker": ticker,
        "note": note,
        "source": SOURCE_MANUAL,
    }


def period_return(dates: list[str], values: list[float], flows: list[dict]) -> dict:
    """Investment result from the first snapshot in ``dates`` through the last.

    ``gain`` is end value minus start value minus net cash flow in
    ``(start, end]``. ``gain_pct`` is the time-weighted return of those same
    days: each day's market move is the value change minus flows that landed
    on that day or, if the flow fell between snapshots, on the next snapshot.
    """
    if not dates or not values:
        return {
            "value_change": 0.0,
            "net_flow": 0.0,
            "gain": 0.0,
            "gain_pct": 0.0,
        }

    start_date = dates[0]
    end_date = dates[-1]
    start_value = float(values[0])
    end_value = float(values[-1])
    net = 0.0
    for flow in flows:
        flow_date = flow["flow_date"]
        if start_date < flow_date <= end_date:
            net += float(flow["amount"])
    net = round(net, 2)
    value_change = round(end_value - start_value, 2)
    gain = round(value_change - net, 2)

    by_day = _flows_by_snapshot(dates, flows)
    factor = 1.0
    for i in range(1, len(dates)):
        begin = float(values[i - 1])
        market = (float(values[i]) - begin) - by_day.get(dates[i], 0.0)
        if abs(begin) > NEGLIGIBLE_VALUE:
            factor *= 1 + market / begin

    return {
        "value_change": value_change,
        "net_flow": net,
        "gain": gain,
        "gain_pct": round((factor - 1) * 100, 2),
    }


def _flows_by_snapshot(dates: list[str], flows: list[dict]) -> dict[str, float]:
    """Sum flows onto the snapshot that first includes them.

    A flow dated on a snapshot belongs to that day. A flow between snapshots
    belongs to the next one, which is the first total that contains the money.
    Flows on or before the first snapshot are already inside the starting value.
    """
    totals: dict[str, float] = defaultdict(float)
    if not dates:
        return totals
    start_date = dates[0]
    end_date = dates[-1]
    for flow in flows:
        flow_date = flow["flow_date"]
        if flow_date <= start_date or flow_date > end_date:
            continue
        target = None
        for day in dates:
            if day >= flow_date:
                target = day
                break
        if target is None or target <= start_date:
            continue
        totals[target] += float(flow["amount"])
    return totals


def _as_dict(row) -> dict:
    return {
        "id": row["id"],
        "flow_date": row["flow_date"],
        "amount": row["amount"],
        "owner": row["owner"],
        "account_type": row["account_type"],
        "ticker": row["ticker"],
        "note": row["note"],
        "source": row["source"],
        "holding_id": row["holding_id"],
    }


def _parse_flow_date(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Date must be YYYY-MM-DD")
    value = value.strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be YYYY-MM-DD") from None
    if parsed > now_local().date():
        raise ValueError("Date cannot be in the future")
    return value


def _parse_flow_amount(value) -> float:
    amount = round(parse_float(value, "Amount"), 2)
    if amount == 0:
        raise ValueError("Amount cannot be zero")
    return amount


def _parse_ticker(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Ticker must be text")
    ticker = value.strip().upper()
    if ticker and ticker != "$$CASH" and not VALID_TICKER.match(ticker):
        raise ValueError("Invalid ticker format")
    return ticker


def _clip(value, limit: int, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value

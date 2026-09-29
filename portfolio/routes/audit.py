"""Audit log API."""

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify

from portfolio.services.audit import RETENTION_DAYS

bp = Blueprint("audit_api", __name__)


@bp.route("/api/audit")
def get_audit_log():
    log_path = current_app.config["AUDIT_LOG"]
    # Older entries are archived off the live file (see services.audit), but
    # filter here too in case the archiver hasn't run yet since a restart.
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    entries = []
    try:
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Format: "2026-02-21 22:22:49 | ADD    | NVDA   | Nvidia Corp. | k=$v  k=$v"
                parts = [p.strip() for p in line.split("|", 4)]
                if len(parts) < 4:
                    continue
                timestamp, action, ticker, name = parts[0], parts[1], parts[2], parts[3]
                if timestamp < cutoff:
                    continue
                raw_fields = parts[4] if len(parts) == 5 else ""

                fields = {}
                for token in raw_fields.split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        fields[k] = v

                entries.append({
                    "timestamp": timestamp,
                    "action": action.strip(),
                    "ticker": ticker.strip(),
                    "name": name.strip(),
                    "fields": fields,
                })
    except FileNotFoundError:
        pass

    entries.reverse()  # newest first
    return jsonify(entries)

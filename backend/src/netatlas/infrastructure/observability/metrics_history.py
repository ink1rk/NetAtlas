"""Build Prometheus-style time series from stored DeviceMetric rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _point(ts: datetime | None, value: float | int | None) -> dict[str, Any] | None:
    if ts is None or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return {"t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts), "v": v}


def _scalar_from_row(row: Any, key: str) -> float | int | None:
    if key in ("cpu_percent", "memory_percent", "temperature_c"):
        return getattr(row, key, None)
    extras = getattr(row, "extras", None) or {}
    if key in extras and extras[key] is not None:
        return extras[key]
    return None


def build_metric_series(rows_asc: list[Any], keys: list[str] | None = None) -> dict[str, Any]:
    """Return series dict for requested metric keys from ascending metric rows."""
    default_keys = [
        "cpu_percent",
        "memory_percent",
        "temperature_c",
        "uptime_seconds",
        "interfaces_total",
        "interfaces_down",
        "if_in_errors",
        "if_out_errors",
        "if_in_discards",
        "if_out_discards",
        "if_in_octets",
        "if_out_octets",
        "if_in_bps",
        "if_out_bps",
    ]
    want = keys or default_keys
    series: dict[str, list[dict[str, Any]]] = {k: [] for k in want}

    prev_ts: datetime | None = None
    prev_in: int | None = None
    prev_out: int | None = None
    prev_if_oct: dict[str, tuple[int | None, int | None]] = {}

    interfaces: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for row in rows_asc:
        ts = getattr(row, "collected_at", None)
        extras = getattr(row, "extras", None) or {}
        for key in want:
            if key in ("if_in_bps", "if_out_bps"):
                continue
            pt = _point(ts, _scalar_from_row(row, key))
            if pt:
                series[key].append(pt)

        # Aggregate bps from sum octets in extras (preferred) or interface counters.
        in_oct = extras.get("if_in_octets")
        out_oct = extras.get("if_out_octets")
        if in_oct is None or out_oct is None:
            counters = extras.get("interface_counters") or []
            if counters:
                in_oct = sum(int(c.get("in_octets") or 0) for c in counters)
                out_oct = sum(int(c.get("out_octets") or 0) for c in counters)
        try:
            in_i = int(in_oct) if in_oct is not None else None
            out_i = int(out_oct) if out_oct is not None else None
        except (TypeError, ValueError):
            in_i, out_i = None, None

        if (
            ts
            and prev_ts
            and in_i is not None
            and prev_in is not None
            and "if_in_bps" in series
        ):
            dt = (ts - prev_ts).total_seconds()
            if dt > 0:
                din = in_i - prev_in
                dout = (out_i - prev_out) if out_i is not None and prev_out is not None else 0
                if din >= 0:
                    series["if_in_bps"].append({"t": ts.isoformat(), "v": round(din * 8 / dt, 2)})
                if dout >= 0 and "if_out_bps" in series:
                    series["if_out_bps"].append({"t": ts.isoformat(), "v": round(dout * 8 / dt, 2)})

        # Per-interface bps
        for c in extras.get("interface_counters") or []:
            name = str(c.get("name") or c.get("if_index") or "").strip()
            if not name:
                continue
            bucket = interfaces.setdefault(
                name,
                {"in_bps": [], "out_bps": [], "in_errors": [], "out_errors": [], "oper_status": []},
            )
            if ts:
                if c.get("in_errors") is not None:
                    bucket["in_errors"].append({"t": ts.isoformat(), "v": float(c.get("in_errors") or 0)})
                if c.get("out_errors") is not None:
                    bucket["out_errors"].append({"t": ts.isoformat(), "v": float(c.get("out_errors") or 0)})
                if c.get("oper_status") is not None:
                    bucket["oper_status"].append(
                        {"t": ts.isoformat(), "v": 1.0 if c.get("oper_status") == "up" else 0.0}
                    )
            try:
                cin = int(c["in_octets"]) if c.get("in_octets") is not None else None
                cout = int(c["out_octets"]) if c.get("out_octets") is not None else None
            except (TypeError, ValueError):
                cin, cout = None, None
            prev = prev_if_oct.get(name)
            if ts and prev_ts and prev and cin is not None and prev[0] is not None:
                dt = (ts - prev_ts).total_seconds()
                if dt > 0:
                    din = cin - prev[0]
                    if din >= 0:
                        bucket["in_bps"].append({"t": ts.isoformat(), "v": round(din * 8 / dt, 2)})
                    if cout is not None and prev[1] is not None:
                        dout = cout - prev[1]
                        if dout >= 0:
                            bucket["out_bps"].append({"t": ts.isoformat(), "v": round(dout * 8 / dt, 2)})
            prev_if_oct[name] = (cin, cout)

        prev_ts = ts
        prev_in = in_i
        prev_out = out_i

    # Drop empty series keys that were never requested with data — keep structure for UI.
    return {
        "series": series,
        "interfaces": interfaces,
    }


def metric_row_dict(row: Any) -> dict[str, Any]:
    extras = dict(getattr(row, "extras", None) or {})
    return {
        "cpu_percent": row.cpu_percent,
        "memory_percent": row.memory_percent,
        "temperature_c": row.temperature_c,
        "uptime_seconds": extras.get("uptime_seconds"),
        "interfaces_total": extras.get("interfaces_total"),
        "interfaces_down": extras.get("interfaces_down"),
        "if_in_errors": extras.get("if_in_errors"),
        "if_out_errors": extras.get("if_out_errors"),
        "if_in_discards": extras.get("if_in_discards"),
        "if_out_discards": extras.get("if_out_discards"),
        "extras": extras,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
        "timestamp": row.collected_at.isoformat() if row.collected_at else None,
    }

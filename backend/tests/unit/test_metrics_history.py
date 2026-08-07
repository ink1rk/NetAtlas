"""Unit tests for Prometheus-style metric series builder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from netatlas.infrastructure.observability.metrics_history import build_metric_series, metric_row_dict


def _row(ts: datetime, cpu: float, in_oct: int, out_oct: int, **extra: object) -> SimpleNamespace:
    extras = {
        "uptime_seconds": 1000,
        "if_in_octets": in_oct,
        "if_out_octets": out_oct,
        "if_in_errors": extra.get("if_in_errors", 0),
        "interface_counters": [
            {
                "name": "ether1",
                "in_octets": in_oct,
                "out_octets": out_oct,
                "in_errors": 1,
                "out_errors": 0,
                "oper_status": "up",
            }
        ],
    }
    return SimpleNamespace(
        cpu_percent=cpu,
        memory_percent=40.0,
        temperature_c=45.0,
        extras=extras,
        collected_at=ts,
    )


def test_build_metric_series_bps_and_gauges() -> None:
    t0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=60)
    t2 = t1 + timedelta(seconds=60)
    rows = [
        _row(t0, 10.0, 1_000_000, 500_000),
        _row(t1, 20.0, 1_000_000 + 7_500_000, 500_000 + 1_500_000),  # 1 Mbps in, 0.2 Mbps out
        _row(t2, 15.0, 1_000_000 + 15_000_000, 500_000 + 3_000_000),
    ]
    built = build_metric_series(rows)
    series = built["series"]
    assert len(series["cpu_percent"]) == 3
    assert series["cpu_percent"][1]["v"] == 20.0
    assert series["temperature_c"][0]["v"] == 45.0
    assert len(series["if_in_bps"]) == 2
    # 7_500_000 octets * 8 / 60 = 1_000_000 bps
    assert series["if_in_bps"][0]["v"] == 1_000_000.0
    assert "ether1" in built["interfaces"]
    assert built["interfaces"]["ether1"]["in_bps"][0]["v"] == 1_000_000.0


def test_metric_row_dict_flattens_uptime() -> None:
    row = _row(datetime.now(UTC), 1.0, 0, 0)
    d = metric_row_dict(row)
    assert d["uptime_seconds"] == 1000
    assert d["cpu_percent"] == 1.0
    assert "interface_counters" in d["extras"]

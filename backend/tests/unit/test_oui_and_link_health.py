"""Unit tests for OUI vendor classification and Link Health scoring."""

from __future__ import annotations

from netatlas.domain.services import LinkHealthScorer
from netatlas.infrastructure.collectors.base.oui import guess_device_type, lookup_oui, normalize_mac


def test_oui_lookup_known_and_unknown() -> None:
    assert lookup_oui("4C:5E:0C:11:22:33") == "Mikrotik"
    assert lookup_oui("18:A6:F7:AA:BB:CC") == "Kyocera"
    assert lookup_oui("00:00:00:00:00:00") is None
    assert lookup_oui(None) is None
    assert lookup_oui("not-a-mac") is None


def test_normalize_mac() -> None:
    assert normalize_mac("4c5e0c112233") == "4c:5e:0c:11:22:33"
    assert normalize_mac("4C-5E-0C-11-22-33") == "4c:5e:0c:11:22:33"
    assert normalize_mac("bad") is None


def test_guess_device_type_heuristics() -> None:
    assert guess_device_type("Kyocera") == "printer"
    assert guess_device_type("Hikvision") == "camera"
    assert guess_device_type("Ubiquiti") == "access_point"
    assert guess_device_type("Mikrotik") == "router"
    assert guess_device_type("Polycom") == "voip_phone"
    assert guess_device_type("Synology") == "nas"
    assert guess_device_type("VMware") == "virtual_machine"
    assert guess_device_type(None, hostname="unknown-host") == "unknown"


def test_link_health_no_telemetry_is_unknown() -> None:
    scorer = LinkHealthScorer()
    status, _reasons = scorer.score(
        iface_a={"oper_status": "unknown"}, iface_b={"oper_status": "unknown"}
    )
    assert status == "unknown"


def test_link_health_healthy_when_up_and_clean() -> None:
    scorer = LinkHealthScorer()
    status, reasons = scorer.score(
        iface_a={"oper_status": "up", "duplex": "full"},
        iface_b={"oper_status": "up", "duplex": "full"},
        counters_a={"in_errors": 0, "in_discards": 0, "out_discards": 0},
        counters_b={"in_errors": 0, "in_discards": 0, "out_discards": 0},
    )
    assert status == "healthy"
    assert "No anomalies detected" in reasons


def test_link_health_critical_when_interface_down() -> None:
    scorer = LinkHealthScorer()
    status, reasons = scorer.score(
        iface_a={"oper_status": "down"}, iface_b={"oper_status": "up"}
    )
    assert status == "critical"
    assert any("down" in r.lower() for r in reasons)


def test_link_health_warning_on_duplex_mismatch() -> None:
    scorer = LinkHealthScorer()
    status, reasons = scorer.score(
        iface_a={"oper_status": "up", "duplex": "half"},
        iface_b={"oper_status": "up", "duplex": "full"},
    )
    assert status == "warning"
    assert any("duplex" in r.lower() for r in reasons)


def test_link_health_critical_on_high_crc() -> None:
    scorer = LinkHealthScorer()
    status, reasons = scorer.score(
        iface_a={"oper_status": "up"},
        iface_b={"oper_status": "up"},
        counters_a={"in_errors": 600},
        counters_b={"in_errors": 0},
    )
    assert status == "critical"
    assert any("crc" in r.lower() for r in reasons)


def test_link_health_optical_power_thresholds() -> None:
    scorer = LinkHealthScorer()
    status, _ = scorer.score(
        iface_a={"oper_status": "up"},
        iface_b={"oper_status": "up"},
        link={"rx_optical_dbm": -25.0},
    )
    assert status == "critical"
    status, _ = scorer.score(
        iface_a={"oper_status": "up"},
        iface_b={"oper_status": "up"},
        link={"rx_optical_dbm": -19.0},
    )
    assert status == "warning"

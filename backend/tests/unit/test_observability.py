"""Tests for onboard observability: syslog parse, categorize, triggers."""

from __future__ import annotations

from netatlas.infrastructure.observability.syslog_parser import categorize_message, parse_syslog


def test_parse_rfc5424() -> None:
    raw = "<34>1 2024-01-15T12:00:00.000Z ideco-fw firewall - - - DENY tcp 10.0.0.5 -> 8.8.8.8"
    parsed = parse_syslog(raw)
    assert parsed.facility == 4
    assert parsed.severity == 2
    assert parsed.hostname == "ideco-fw"
    assert parsed.app_name == "firewall"
    assert "DENY" in parsed.message
    assert parsed.extras["format"] == "rfc5424"


def test_parse_rfc3164() -> None:
    raw = "<134>Jan 15 12:00:01 mes-core LINK-3-UPDOWN: Interface Gi1/0/24 changed state to down"
    parsed = parse_syslog(raw)
    assert parsed.extras["format"] == "rfc3164"
    assert parsed.hostname == "mes-core"
    assert "Interface" in parsed.message


def test_categorize_auth_and_firewall() -> None:
    cat, tags = categorize_message("Failed password for root from 1.2.3.4", severity=4, app_name="sshd")
    assert cat == "auth_failure"
    assert "security" in tags

    cat2, tags2 = categorize_message("firewall deny packet dropped", severity=5, app_name=None)
    assert cat2 == "firewall"
    assert "security" in tags2


def test_categorize_link_down() -> None:
    cat, tags = categorize_message("Interface Gi1/0/24 went down", severity=3, app_name="eltex")
    assert cat == "link_down"
    assert "network" in tags

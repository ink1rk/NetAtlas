"""Device upsert must not wipe rich inventory with LLDP/unknown stubs."""

from __future__ import annotations

from netatlas.infrastructure.persistence.repositories import _prefer_str


def test_prefer_str_keeps_rich_identity() -> None:
    assert _prefer_str("unknown", "CRS354-48P-4S+2Q+") == "CRS354-48P-4S+2Q+"
    assert _prefer_str("generic", "mikrotik", empty=("unknown", "generic", "")) == "mikrotik"
    assert _prefer_str("core-sw", "10.0.0.1") == "core-sw"
    assert _prefer_str("", "sw1") == "sw1"
    assert _prefer_str("sw1", "") == "sw1"

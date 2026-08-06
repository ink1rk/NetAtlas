"""Unit tests for Mikrotik RouterOS CLI parsing (Bridge View, VLANs, routes)."""

from __future__ import annotations

from netatlas.infrastructure.collectors.mikrotik.plugin import (
    _parse_bridge_view,
    _parse_routes,
    _parse_vlan_print,
)

VLAN_PRINT = """Flags: X - disabled, R - running
 0  R name="vlan10-office" mtu=1500 arp=enabled interface=bridge1 vlan-id=10
 1    name="vlan20-guest" mtu=1500 arp=enabled interface=bridge1 vlan-id=20
"""

BRIDGE_PRINT = """Flags: X - disabled
 0    name="bridge1" mtu=1500 protocol-mode=rstp vlan-filtering=yes
"""

BRIDGE_PORTS = """Flags: X - disabled, I - inactive, D - dynamic
 0    interface=ether2 bridge=bridge1 pvid=10 horizon=none
 1    interface=ether3 bridge=bridge1 pvid=1 horizon=none
"""

BRIDGE_VLANS = """ 0   bridge=bridge1 vlan-ids=10 tagged=ether2 untagged=ether3
 1   bridge=bridge1 vlan-ids=20 tagged=ether2,ether4 untagged=
"""

ROUTE_PRINT = """Flags: X - disabled, A - active, D - dynamic, C - connect, S - static
 0 A S  dst-address=0.0.0.0/0 gateway=192.168.1.1 gateway-status=192.168.1.1 reachable via  ether1 distance=1
 1 A C  dst-address=192.168.1.0/24 gateway=ether1 distance=0
"""


def test_parse_vlan_print() -> None:
    vlans = _parse_vlan_print(VLAN_PRINT)
    assert {"vlan_id": 10, "name": "vlan10-office"} in vlans
    assert {"vlan_id": 20, "name": "vlan20-guest"} in vlans


def test_parse_bridge_view() -> None:
    bridge = _parse_bridge_view(BRIDGE_PRINT, BRIDGE_PORTS, BRIDGE_VLANS)
    assert bridge["bridges"] == [{"name": "bridge1", "rstp": "rstp", "vlan_filtering": True}]
    ports_by_name = {p["interface"]: p for p in bridge["ports"]}
    assert ports_by_name["ether2"]["pvid"] == 10
    assert ports_by_name["ether3"]["pvid"] == 1
    vlan10 = next(v for v in bridge["vlan_table"] if v["vlan_id"] == 10)
    assert vlan10["tagged"] == ["ether2"]
    assert vlan10["untagged"] == ["ether3"]


def test_parse_bridge_view_empty() -> None:
    assert _parse_bridge_view(None, None, None) == {}


def test_parse_routes() -> None:
    routes = _parse_routes(ROUTE_PRINT)
    assert any(r["destination"] == "0.0.0.0/0" and r["next_hop"] == "192.168.1.1" for r in routes)
    assert any(r["destination"] == "192.168.1.0/24" and r["protocol"] == "connected" for r in routes)

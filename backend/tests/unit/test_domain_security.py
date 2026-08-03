"""Unit tests for domain services and security primitives."""

from __future__ import annotations

import base64
import os
from uuid import uuid4

import pytest

from netatlas.domain.errors import WriteOperationForbiddenError
from netatlas.domain.services import CablePathResolver, SnapshotChecksum, SnapshotComparer, TopologyBuilder
from netatlas.domain.value_objects import IpNetworkVO, MacAddress, VlanId
from netatlas.infrastructure.security.readonly_guard import ReadOnlyCommandGuard, SnmpReadOnlyGuard
from netatlas.infrastructure.security.vault import AesGcmSecretVault


def test_mac_normalization() -> None:
    assert str(MacAddress("AA-BB-CC-DD-EE-FF")) == "aa:bb:cc:dd:ee:ff"
    assert str(MacAddress("aabbccddeeff")) == "aa:bb:cc:dd:ee:ff"


def test_vlan_bounds() -> None:
    assert VlanId(100).value == 100
    with pytest.raises(ValueError):
        VlanId(5000)


def test_ip_network_hosts() -> None:
    hosts = IpNetworkVO("10.0.0.0/30").hosts()
    assert "10.0.0.1" in hosts
    assert "10.0.0.2" in hosts


def test_topology_builder_and_cable_path() -> None:
    d1, d2, d3 = str(uuid4()), str(uuid4()), str(uuid4())
    i1, i2, i3, i4 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    devices = [
        {"id": d1, "hostname": "core", "platform": "cisco_ios"},
        {"id": d2, "hostname": "access", "platform": "eltex"},
        {"id": d3, "hostname": "server", "platform": "linux"},
    ]
    interfaces = {
        i1: {"id": i1, "device_id": d1, "name": "Gi0/1"},
        i2: {"id": i2, "device_id": d2, "name": "Gi1/0/24"},
        i3: {"id": i3, "device_id": d2, "name": "Gi1/0/1"},
        i4: {"id": i4, "device_id": d3, "name": "eth0"},
    }
    links = [
        {"id": str(uuid4()), "interface_a_id": i1, "interface_b_id": i2, "speed_bps": 1_000_000_000},
        {"id": str(uuid4()), "interface_a_id": i3, "interface_b_id": i4, "speed_bps": 1_000_000_000},
    ]
    nodes, edges = TopologyBuilder().build(devices, links, interfaces)
    assert len(nodes) == 3
    assert len(edges) == 2

    hops = CablePathResolver().resolve(
        from_device_id=type("U", (), {"__str__": lambda self: d1})(),  # type: ignore[misc]
        to_device_id=type("U", (), {"__str__": lambda self: d3})(),  # type: ignore[misc]
        devices={d["id"]: d for d in devices},
        links=links,
        interfaces_by_id=interfaces,
    )
    # CablePathResolver expects UUID objects — use real UUIDs
    from uuid import UUID

    hops = CablePathResolver().resolve(
        from_device_id=UUID(d1),
        to_device_id=UUID(d3),
        devices={d["id"]: d for d in devices},
        links=links,
        interfaces_by_id=interfaces,
    )
    assert [h.hostname for h in hops] == ["core", "access", "server"]


def test_snapshot_diff_and_checksum() -> None:
    left = {
        "devices": [{"hostname": "sw1", "serial": "A1", "firmware": "1.0"}],
        "links": [],
        "vlans": [{"device": "sw1", "vlan_id": 10}],
        "interfaces": [{"device": "sw1", "name": "Gi0/1", "oper_status": "up"}],
    }
    right = {
        "devices": [
            {"hostname": "sw1", "serial": "A1", "firmware": "1.1"},
            {"hostname": "sw2", "serial": "B2", "firmware": "1.0"},
        ],
        "links": [],
        "vlans": [{"device": "sw1", "vlan_id": 10}, {"device": "sw1", "vlan_id": 333}],
        "interfaces": [{"device": "sw1", "name": "Gi0/1", "oper_status": "down"}],
    }
    report = SnapshotComparer().compare(left, right)
    assert any(x["section"] == "devices" for x in report["added"])
    assert any(x["section"] == "vlans" for x in report["added"])
    assert any(x["section"] == "devices" for x in report["changed"])
    assert any(x["section"] == "interfaces" for x in report["changed"])
    assert SnapshotChecksum.compute(left) != SnapshotChecksum.compute(right)


def test_aes_gcm_vault_roundtrip() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    vault = AesGcmSecretVault(key)
    ct, nonce, ver = vault.encrypt(b'{"community":"secret"}')
    assert vault.decrypt(ct, nonce, key_version=ver) == b'{"community":"secret"}'


def test_readonly_ssh_guard() -> None:
    guard = ReadOnlyCommandGuard()
    guard.assert_allowed("show version", platform="cisco_ios")
    with pytest.raises(WriteOperationForbiddenError):
        guard.assert_allowed("configure terminal", platform="cisco_ios")
    with pytest.raises(WriteOperationForbiddenError):
        guard.assert_allowed("write memory", platform="cisco_ios")
    with pytest.raises(WriteOperationForbiddenError):
        guard.assert_allowed("reload", platform="cisco_ios")


def test_snmp_set_blocked() -> None:
    guard = SnmpReadOnlyGuard()
    guard.assert_allowed("get")
    guard.assert_allowed("walk")
    with pytest.raises(WriteOperationForbiddenError):
        guard.assert_allowed("set")


def test_collector_registry_resolves_cisco() -> None:
    from netatlas.domain.ports import DeviceFingerprint
    from netatlas.infrastructure.collectors.base.registry import build_default_registry

    registry = build_default_registry()
    plugin = registry.resolve(
        DeviceFingerprint(management_ip="10.0.0.1", sys_descr="Cisco IOS Software, C9300")
    )
    assert plugin.vendor == "cisco"

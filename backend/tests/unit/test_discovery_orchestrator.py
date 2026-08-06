"""Unit tests for DiscoveryOrchestrator: scan_mode gating, Unknown Device
fallback (OUI classification), and Credential Manager rotation.

Uses fully in-memory fake repositories (no DB/network) — the orchestrator only
depends on Protocol-typed ports, so this exercises real application logic.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from netatlas.application.use_cases import discovery as discovery_mod
from netatlas.application.use_cases.discovery import (
    DiscoveryOrchestrator,
    _guess_media,
    _is_generic_signal,
)
from netatlas.domain.entities import Device, DiscoveryJob, DiscoverySeed, Interface, Link
from netatlas.domain.ports import (
    ArpEntry,
    CollectorContext,
    DeviceFingerprint,
    FdbEntry,
    InventoryFacts,
    NeighborFact,
)
from netatlas.domain.value_objects import DevicePlatform, JobStatus


class FakeJobRepo:
    def __init__(self) -> None:
        self.jobs: dict[UUID, DiscoveryJob] = {}

    async def add(self, job: DiscoveryJob) -> DiscoveryJob:
        self.jobs[job.id] = job
        return job

    async def get(self, job_id: UUID) -> DiscoveryJob | None:
        return self.jobs.get(job_id)

    async def list(self) -> list[DiscoveryJob]:
        return list(self.jobs.values())

    async def update(self, job: DiscoveryJob) -> DiscoveryJob:
        self.jobs[job.id] = job
        return job


class FakeSeedRepo:
    def __init__(self, seeds: list[DiscoverySeed]) -> None:
        self._seeds = seeds

    async def list(self) -> list[DiscoverySeed]:
        return self._seeds

    async def add(self, seed: DiscoverySeed) -> DiscoverySeed:
        self._seeds.append(seed)
        return seed

    async def delete(self, seed_id: UUID) -> None:
        self._seeds = [s for s in self._seeds if s.id != seed_id]

    async def get_many(self, seed_ids: list[UUID]) -> list[DiscoverySeed]:
        if not seed_ids:
            return self._seeds
        return [s for s in self._seeds if s.id in seed_ids]


class FakeDeviceRepo:
    def __init__(self) -> None:
        self.by_ip: dict[str, Device] = {}

    async def get(self, device_id: UUID) -> Device | None:
        return next((d for d in self.by_ip.values() if d.id == device_id), None)

    async def list(self, *, page: int, page_size: int, q: str | None = None, vendor: str | None = None) -> tuple[list[Device], int]:
        items = list(self.by_ip.values())
        return items, len(items)

    async def upsert_by_identity(self, device: Device) -> Device:
        if device.management_ip and device.management_ip in self.by_ip:
            existing = self.by_ip[device.management_ip]
            device.id = existing.id
        self.by_ip[device.management_ip] = device
        return device

    async def search(self, query: str, *, limit: int = 50) -> list[Device]:
        return list(self.by_ip.values())[:limit]


class FakeInterfaceRepo:
    def __init__(self) -> None:
        self.by_device: dict[UUID, list[Interface]] = {}

    async def list_for_device(self, device_id: UUID) -> list[Interface]:
        return self.by_device.get(device_id, [])

    async def replace_for_device(self, device_id: UUID, interfaces: list[Interface]) -> None:
        self.by_device[device_id] = interfaces


class FakeLinkRepo:
    def __init__(self) -> None:
        self.links: list[Link] = []

    async def list_all(self) -> list[Link]:
        return self.links

    async def upsert(self, link: Link) -> Link:
        self.links.append(link)
        return link


class FakeSnapshotRepo:
    def __init__(self) -> None:
        self.snapshots: list[Any] = []

    async def add(self, snapshot: Any) -> Any:
        self.snapshots.append(snapshot)
        return snapshot

    async def get(self, snapshot_id: UUID) -> Any | None:
        return next((s for s in self.snapshots if s.id == snapshot_id), None)

    async def list(self) -> list[Any]:
        return self.snapshots


class FakeWriterRepo:
    """Generic replace_for_device recorder used for Neighbor/Fdb/Arp/Vlan/Route ports."""

    def __init__(self) -> None:
        self.calls: dict[UUID, list[Any]] = {}

    async def replace_for_device(self, device_id: UUID, items: list[Any]) -> None:
        self.calls[device_id] = items


class FakePlugin:
    """A plugin that reports full adjacency facts for a healthy switch."""

    vendor = "fake"
    platforms = frozenset({"fake"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        return True

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        return InventoryFacts(
            hostname=f"sw-{ctx.target_ip}",
            vendor="fake",
            model="FakeSwitch",
            serial="SN123",
            firmware="1.0",
            os_version="1.0",
            management_mac="aa:bb:cc:dd:ee:ff",
            platform=DevicePlatform.UNKNOWN,
            attributes={},
            interfaces=[
                {"name": "eth0", "if_index": "1", "oper_status": "up", "admin_status": "up", "speed_bps": 1_000_000_000}
            ],
            vlans=[{"vlan_id": 10, "name": "office"}],
        )

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        return [
            NeighborFact(
                local_interface="eth0",
                remote_hostname="core-sw",
                remote_interface="eth1",
                remote_chassis_id=None,
                remote_mgmt_ip="10.0.0.254",
                protocol="lldp",
            )
        ]

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        return [FdbEntry(mac="11:22:33:44:55:66", vlan_id=10, interface="eth0")]

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        return [ArpEntry(ip="10.0.0.5", mac="11:22:33:44:55:66", interface="eth0")]

    async def collect_metrics(self, ctx: CollectorContext) -> Any:
        raise NotImplementedError


class FakeGenericPlugin(FakePlugin):
    """Simulates a closed/unmanaged host — SNMP answers nothing usable."""

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        return InventoryFacts(
            hostname=ctx.target_ip,
            vendor="generic",
            model="unknown",
            serial=None,
            firmware=None,
            os_version=None,
            management_mac=None,
            platform=DevicePlatform.UNKNOWN,
            attributes={},
            interfaces=[],
        )


class FakeRegistry:
    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    def resolve(self, fingerprint: DeviceFingerprint) -> Any:
        return self._plugin

    def all(self) -> list[Any]:
        return [self._plugin]


def _make_orchestrator(plugin: Any, *, with_writers: bool = True) -> tuple[DiscoveryOrchestrator, dict[str, Any]]:
    repos = {
        "jobs": FakeJobRepo(),
        "devices": FakeDeviceRepo(),
        "interfaces": FakeInterfaceRepo(),
        "links": FakeLinkRepo(),
        "snapshots": FakeSnapshotRepo(),
        "neighbors": FakeWriterRepo(),
        "fdb": FakeWriterRepo(),
        "arp": FakeWriterRepo(),
        "vlans": FakeWriterRepo(),
        "routes": FakeWriterRepo(),
    }

    async def credential_loader(seeds: list[Any]) -> dict[str, Any]:
        return {"snmp": {"community": "public", "version": 2}}

    orch = DiscoveryOrchestrator(
        jobs=repos["jobs"],
        seeds=FakeSeedRepo([]),
        devices=repos["devices"],
        interfaces=repos["interfaces"],
        links=repos["links"],
        snapshots=repos["snapshots"],
        registry=FakeRegistry(plugin),
        credential_loader=credential_loader,
        neighbors=repos["neighbors"] if with_writers else None,
        fdb=repos["fdb"] if with_writers else None,
        arp=repos["arp"] if with_writers else None,
        vlans=repos["vlans"] if with_writers else None,
        routes=repos["routes"] if with_writers else None,
    )
    return orch, repos


def _job(scan_mode: str, target: str = "10.0.0.1") -> tuple[DiscoveryJob, DiscoverySeed]:
    seed = DiscoverySeed(id=uuid4(), target=target, label="t", enabled=True)
    job = DiscoveryJob(
        id=uuid4(),
        status=JobStatus.PENDING,
        started_at=None,
        finished_at=None,
        config={"seed_ids": [str(seed.id)], "scan_mode": scan_mode, "icmp_timeout": 0.1},
        stats={},
    )
    return job, seed


@pytest.mark.asyncio
async def test_deep_scan_persists_adjacency_and_vlans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "icmp_probe", _always_alive)
    orch, repos = _make_orchestrator(FakePlugin())
    job, seed = _job("deep")
    repos["jobs"].jobs[job.id] = job
    orch._seeds = FakeSeedRepo([seed])  # type: ignore[attr-defined]

    result = await orch.run(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.stats["inventoried"] == 1
    assert result.stats["links"] == 1
    # Adjacency persisted
    assert any(repos["fdb"].calls.values())
    assert any(repos["arp"].calls.values())
    assert any(repos["neighbors"].calls.values())
    assert any(repos["vlans"].calls.values())


@pytest.mark.asyncio
async def test_fast_scan_skips_adjacency_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "icmp_probe", _always_alive)
    orch, repos = _make_orchestrator(FakePlugin())
    job, seed = _job("fast")
    repos["jobs"].jobs[job.id] = job
    orch._seeds = FakeSeedRepo([seed])  # type: ignore[attr-defined]

    result = await orch.run(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.stats["inventoried"] == 1
    assert result.stats["links"] == 0
    assert repos["fdb"].calls == {}
    assert repos["neighbors"].calls == {}
    assert repos["vlans"].calls == {}


@pytest.mark.asyncio
async def test_topology_scan_collects_adjacency_but_skips_vlans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "icmp_probe", _always_alive)
    orch, repos = _make_orchestrator(FakePlugin())
    job, seed = _job("topology")
    repos["jobs"].jobs[job.id] = job
    orch._seeds = FakeSeedRepo([seed])  # type: ignore[attr-defined]

    result = await orch.run(job.id)

    assert result.stats["links"] == 1
    assert any(repos["fdb"].calls.values())
    assert repos["vlans"].calls == {}


@pytest.mark.asyncio
async def test_unknown_device_created_when_collector_has_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "icmp_probe", _always_alive)
    monkeypatch.setattr(discovery_mod, "resolve_local_mac", _fake_resolve_local_mac)
    monkeypatch.setattr(discovery_mod, "reverse_dns", _fake_reverse_dns)
    orch, repos = _make_orchestrator(FakeGenericPlugin())
    job, seed = _job("deep")
    repos["jobs"].jobs[job.id] = job
    orch._seeds = FakeSeedRepo([seed])  # type: ignore[attr-defined]

    result = await orch.run(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.stats.get("unknown_devices") == 1
    device = repos["devices"].by_ip["10.0.0.1"]
    assert device.model == "Unknown Device"
    assert device.vendor == "Mikrotik"  # OUI-resolved from the fake local ARP MAC
    assert device.attributes["auto_classified"] is True
    assert device.attributes["device_class"] == "router"


@pytest.mark.asyncio
async def test_credential_rotation_picks_working_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "icmp_probe", _always_alive)

    calls: list[dict[str, Any]] = []

    async def fake_snmp_get_pair(self: DiscoveryOrchestrator, target: str, snmp: dict[str, Any]) -> tuple[str | None, str | None]:
        calls.append(snmp)
        if snmp.get("community") == "correct-community":
            return "Fake Switch sysDescr", "1.3.6.1.4.1.9999"
        return None, None

    monkeypatch.setattr(DiscoveryOrchestrator, "_snmp_get_pair", fake_snmp_get_pair)

    orch, repos = _make_orchestrator(FakePlugin())
    job, seed = _job("deep")
    repos["jobs"].jobs[job.id] = job
    orch._seeds = FakeSeedRepo([seed])  # type: ignore[attr-defined]

    async def candidates_loader(seeds: list[Any]) -> list[dict[str, Any]]:
        return [
            {"snmp": {"community": "wrong-1", "version": 2}, "_profile_id": "profile-wrong-1"},
            {"snmp": {"community": "correct-community", "version": 2}, "_profile_id": "profile-correct"},
            {"snmp": {"community": "public", "version": 2}},
        ]

    orch._credential_candidates_loader = candidates_loader  # type: ignore[attr-defined]

    result = await orch.run(job.id)

    assert result.status == JobStatus.COMPLETED
    device = repos["devices"].by_ip["10.0.0.1"]
    assert device.attributes["verified_credential_profile_id"] == "profile-correct"
    # Rotation stopped at the first working candidate — should not have tried the fallback default.
    assert {c.get("community") for c in calls} == {"wrong-1", "correct-community"}


def test_guess_media_heuristics() -> None:
    assert _guess_media("sfp-sfpplus1") == "fiber"
    assert _guess_media("GigabitEthernet0/1") == "copper"
    assert _guess_media(None) == "unknown"


def test_is_generic_signal() -> None:
    generic = InventoryFacts(
        hostname="1.2.3.4",
        vendor="generic",
        model="unknown",
        serial=None,
        firmware=None,
        os_version=None,
        management_mac=None,
        platform=DevicePlatform.UNKNOWN,
        interfaces=[],
    )
    assert _is_generic_signal(generic) is True

    with_signal = InventoryFacts(
        hostname="sw1",
        vendor="eltex",
        model="MES3324",
        serial="X1",
        firmware="1.0",
        os_version="1.0",
        management_mac=None,
        platform=DevicePlatform.ELTEX,
        interfaces=[{"name": "eth0"}],
    )
    assert _is_generic_signal(with_signal) is False


async def _always_alive(host: str, *, timeout: float = 1.0, count: int = 1) -> bool:
    return True


async def _fake_resolve_local_mac(ip: str, *, timeout: float = 1.5) -> str | None:
    return "4c:5e:0c:11:22:33"  # Mikrotik OUI


async def _fake_reverse_dns(ip: str, *, timeout: float = 1.0) -> str | None:
    return None

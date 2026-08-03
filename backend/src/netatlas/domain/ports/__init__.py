"""Domain ports (interfaces)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from netatlas.domain.entities import Device, DiscoveryJob, DiscoverySeed, Interface, Link, Snapshot
from netatlas.domain.value_objects import DevicePlatform


@dataclass(slots=True)
class DeviceFingerprint:
    management_ip: str
    sys_descr: str | None = None
    sys_object_id: str | None = None
    ssh_banner: str | None = None
    hints: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InventoryFacts:
    hostname: str
    vendor: str
    model: str
    serial: str | None
    firmware: str | None
    os_version: str | None
    management_mac: str | None
    platform: DevicePlatform
    attributes: dict[str, Any] = field(default_factory=dict)
    interfaces: list[dict[str, Any]] = field(default_factory=list)
    vlans: list[dict[str, Any]] = field(default_factory=list)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    temperature_c: float | None = None
    uptime_seconds: int | None = None


@dataclass(slots=True)
class NeighborFact:
    local_interface: str
    remote_hostname: str | None
    remote_interface: str | None
    remote_chassis_id: str | None
    remote_mgmt_ip: str | None
    protocol: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FdbEntry:
    mac: str
    vlan_id: int | None
    interface: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArpEntry:
    ip: str
    mac: str
    interface: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricsSample:
    cpu_percent: float | None = None
    memory_percent: float | None = None
    temperature_c: float | None = None
    interface_counters: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class CollectorContext:
    target_ip: str
    credentials: dict[str, Any]
    timeouts: dict[str, float]
    # Transport callables injected by infrastructure; always read-only.
    snmp_get: Any = None
    snmp_walk: Any = None
    ssh_exec: Any = None
    http_get: Any = None


class CollectorPlugin(Protocol):
    vendor: str
    platforms: frozenset[str]

    def supports(self, fingerprint: DeviceFingerprint) -> bool: ...

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts: ...

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]: ...

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: ...

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: ...

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: ...


class DeviceRepository(Protocol):
    async def get(self, device_id: UUID) -> Device | None: ...
    async def list(
        self, *, page: int, page_size: int, q: str | None = None, vendor: str | None = None
    ) -> tuple[list[Device], int]: ...
    async def upsert_by_identity(self, device: Device) -> Device: ...
    async def search(self, query: str, *, limit: int = 50) -> list[Device]: ...


class InterfaceRepository(Protocol):
    async def list_for_device(self, device_id: UUID) -> list[Interface]: ...
    async def replace_for_device(self, device_id: UUID, interfaces: list[Interface]) -> None: ...


class LinkRepository(Protocol):
    async def list_all(self) -> list[Link]: ...
    async def upsert(self, link: Link) -> Link: ...


class SnapshotRepository(Protocol):
    async def add(self, snapshot: Snapshot) -> Snapshot: ...
    async def get(self, snapshot_id: UUID) -> Snapshot | None: ...
    async def list(self) -> list[Snapshot]: ...


class DiscoverySeedRepository(Protocol):
    async def list(self) -> list[DiscoverySeed]: ...
    async def add(self, seed: DiscoverySeed) -> DiscoverySeed: ...
    async def delete(self, seed_id: UUID) -> None: ...
    async def get_many(self, seed_ids: list[UUID]) -> list[DiscoverySeed]: ...


class DiscoveryJobRepository(Protocol):
    async def add(self, job: DiscoveryJob) -> DiscoveryJob: ...
    async def get(self, job_id: UUID) -> DiscoveryJob | None: ...
    async def list(self) -> list[DiscoveryJob]: ...
    async def update(self, job: DiscoveryJob) -> DiscoveryJob: ...


class SecretVault(Protocol):
    def encrypt(self, plaintext: bytes, *, key_version: str = "v1") -> tuple[bytes, bytes, str]: ...
    def decrypt(self, ciphertext: bytes, nonce: bytes, *, key_version: str = "v1") -> bytes: ...


class AuditLogger(Protocol):
    async def log(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        source_ip: str | None,
        details: dict[str, Any] | None = None,
    ) -> None: ...

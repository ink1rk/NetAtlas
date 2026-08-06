"""Domain entities (pure dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from netatlas.domain.value_objects import (
    DevicePlatform,
    DeviceStatus,
    DiscoveryMethod,
    JobStatus,
)


@dataclass(slots=True)
class Device:
    id: UUID
    hostname: str
    vendor: str
    model: str
    serial: str | None
    firmware: str | None
    os_version: str | None
    management_ip: str | None
    management_mac: str | None
    platform: DevicePlatform
    status: DeviceStatus
    site_id: UUID | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    network_role: str = "unknown"
    role_confidence: float = 0.0
    role_reasons: list[Any] = field(default_factory=list)
    role_source: str = "auto"
    location: str | None = None
    rack: str | None = None
    owner: str | None = None
    criticality: str = "normal"
    description: str | None = None


@dataclass(slots=True)
class Interface:
    id: UUID
    device_id: UUID
    name: str
    if_index: str | None
    description: str | None
    mac: str | None
    mtu: int | None
    duplex: str | None
    speed_bps: int | None
    poe_enabled: bool
    admin_status: str
    oper_status: str
    is_trunk: bool
    native_vlan: int | None
    lacp_group: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Link:
    id: UUID
    interface_a_id: UUID
    interface_b_id: UUID
    discovery_method: DiscoveryMethod
    speed_bps: int | None
    is_lacp: bool
    lacp_key: str | None
    is_trunk: bool
    vlans: list[int]
    confidence: float
    last_confirmed_at: datetime | None = None
    # Interface-centric enrichment (additive — populated best-effort at discovery time)
    media: str = "unknown"  # fiber | copper | unknown
    link_status: str = "unknown"  # up | down | degraded | unknown
    crc_errors: int | None = None
    drops: int | None = None
    rx_utilization_pct: float | None = None
    tx_utilization_pct: float | None = None
    sfp_vendor: str | None = None
    sfp_model: str | None = None
    sfp_serial: str | None = None
    rx_optical_dbm: float | None = None
    tx_optical_dbm: float | None = None
    temperature_c: float | None = None
    voltage: float | None = None
    # Link Health (computed lazily by LinkHealthScorer, cached here at read-time)
    health: str = "unknown"  # healthy | warning | critical | unknown
    health_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiscoverySeed:
    id: UUID
    target: str
    label: str | None
    enabled: bool
    credential_profile_ids: list[UUID] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveryJob:
    id: UUID
    status: JobStatus
    started_at: datetime | None
    finished_at: datetime | None
    config: dict[str, Any]
    stats: dict[str, Any]
    error: str | None = None


@dataclass(slots=True)
class Snapshot:
    id: UUID
    discovery_job_id: UUID | None
    label: str
    created_at: datetime
    checksum: str
    summary: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)

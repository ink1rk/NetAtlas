"""Repository adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.domain.entities import Device, DiscoveryJob, DiscoverySeed, Interface, Link, Snapshot
from netatlas.domain.ports import ArpEntry, FdbEntry, NeighborFact, RouteFact
from netatlas.domain.value_objects import DevicePlatform, DeviceStatus, DiscoveryMethod, JobStatus
from netatlas.infrastructure.persistence.models import (
    ArpEntryModel,
    DeviceModel,
    DiscoveryJobModel,
    DiscoverySeedModel,
    FdbEntryModel,
    InterfaceModel,
    IpAddressModel,
    LinkModel,
    LldpNeighborModel,
    RouteModel,
    SnapshotModel,
    VlanModel,
)


_EMPTY_IDENTITY = frozenset({"", "unknown", "unknown device", "generic", "none"})


def _prefer_str(new: str | None, old: str | None, *, empty: tuple[str, ...] | frozenset[str] = _EMPTY_IDENTITY) -> str:
    """Keep the richer of two identity strings (never overwrite good data with stubs)."""
    new_s = (new or "").strip()
    old_s = (old or "").strip()
    if not new_s or new_s.lower() in empty:
        return old_s or new_s
    if not old_s or old_s.lower() in empty:
        return new_s
    # Prefer non-IP hostname over bare IP when both look set
    return new_s


def _device_from_model(m: DeviceModel) -> Device:
    return Device(
        id=m.id,
        hostname=m.hostname,
        vendor=m.vendor,
        model=m.model,
        serial=m.serial,
        firmware=m.firmware,
        os_version=m.os_version,
        management_ip=str(m.management_ip) if m.management_ip else None,
        management_mac=str(m.management_mac) if m.management_mac else None,
        platform=DevicePlatform(m.platform) if m.platform in DevicePlatform._value2member_map_ else DevicePlatform.UNKNOWN,
        status=DeviceStatus(m.status) if m.status in DeviceStatus._value2member_map_ else DeviceStatus.UNKNOWN,
        site_id=m.site_id,
        first_seen_at=m.first_seen_at,
        last_seen_at=m.last_seen_at,
        attributes=dict(m.attributes or {}),
        network_role=getattr(m, "network_role", None) or "unknown",
        role_confidence=float(getattr(m, "role_confidence", 0) or 0),
        role_reasons=list(getattr(m, "role_reasons", None) or []),
        role_source=getattr(m, "role_source", None) or "auto",
        location=getattr(m, "location", None),
        rack=getattr(m, "rack", None),
        owner=getattr(m, "owner", None),
        criticality=getattr(m, "criticality", None) or "normal",
        description=getattr(m, "description", None),
    )


class SqlAlchemyDeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, device_id: UUID) -> Device | None:
        m = await self._session.get(DeviceModel, device_id)
        return _device_from_model(m) if m else None

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        q: str | None = None,
        vendor: str | None = None,
        status: str | None = None,
        platform: str | None = None,
    ) -> tuple[list[Device], int]:
        from sqlalchemy import String, cast

        stmt = select(DeviceModel)
        count_stmt = select(func.count()).select_from(DeviceModel)
        if q:
            like = f"%{q}%"
            filt = or_(
                DeviceModel.hostname.ilike(like),
                DeviceModel.serial.ilike(like),
                DeviceModel.model.ilike(like),
                DeviceModel.vendor.ilike(like),
                DeviceModel.platform.ilike(like),
                cast(DeviceModel.management_ip, String).ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        if vendor:
            stmt = stmt.where(DeviceModel.vendor.ilike(f"%{vendor}%"))
            count_stmt = count_stmt.where(DeviceModel.vendor.ilike(f"%{vendor}%"))
        if status:
            stmt = stmt.where(DeviceModel.status == status)
            count_stmt = count_stmt.where(DeviceModel.status == status)
        if platform:
            stmt = stmt.where(DeviceModel.platform.ilike(f"%{platform}%"))
            count_stmt = count_stmt.where(DeviceModel.platform.ilike(f"%{platform}%"))
        total = int((await self._session.execute(count_stmt)).scalar_one())
        rows = (
            await self._session.execute(
                stmt.order_by(DeviceModel.hostname).offset((page - 1) * page_size).limit(page_size)
            )
        ).scalars().all()
        return [_device_from_model(r) for r in rows], total

    async def upsert_by_identity(self, device: Device) -> Device:
        existing: DeviceModel | None = None
        if device.serial:
            existing = (
                await self._session.execute(
                    select(DeviceModel).where(
                        DeviceModel.serial == device.serial, DeviceModel.vendor == device.vendor
                    )
                )
            ).scalar_one_or_none()
        if existing is None and device.management_ip:
            existing = (
                await self._session.execute(
                    select(DeviceModel).where(DeviceModel.management_ip == device.management_ip)
                )
            ).scalar_one_or_none()
        now = datetime.now(UTC)
        if existing is None:
            existing = DeviceModel(id=device.id or uuid4())
            existing.first_seen_at = now
            self._session.add(existing)
            existing.hostname = device.hostname
            existing.vendor = device.vendor
            existing.model = device.model
            existing.serial = device.serial
            existing.firmware = device.firmware
            existing.os_version = device.os_version
            existing.management_ip = device.management_ip
            existing.management_mac = device.management_mac
            existing.platform = device.platform.value
            existing.status = device.status.value
            existing.attributes = device.attributes or {}
        else:
            # Never let LLDP stubs / Unknown Device wipe a richer inventory.
            existing.hostname = _prefer_str(device.hostname, existing.hostname)
            existing.vendor = _prefer_str(device.vendor, existing.vendor, empty=("unknown", "generic", ""))
            existing.model = _prefer_str(
                device.model, existing.model, empty=("unknown", "unknown device", "")
            )
            existing.serial = device.serial or existing.serial
            existing.firmware = device.firmware or existing.firmware
            existing.os_version = device.os_version or existing.os_version
            existing.management_ip = device.management_ip or existing.management_ip
            existing.management_mac = device.management_mac or existing.management_mac
            new_plat = device.platform.value if hasattr(device.platform, "value") else str(device.platform)
            if new_plat and new_plat != "unknown":
                existing.platform = new_plat
            new_status = device.status.value if hasattr(device.status, "value") else str(device.status)
            if new_status and new_status != "unknown":
                existing.status = new_status
            merged_attrs = dict(existing.attributes or {})
            incoming = dict(device.attributes or {})
            # Drop auto_classified once we have a real inventory signal.
            if incoming and not incoming.get("auto_classified"):
                merged_attrs.pop("auto_classified", None)
            merged_attrs.update(incoming)
            existing.attributes = merged_attrs
        existing.last_seen_at = now
        await self._session.flush()
        return _device_from_model(existing)

    async def search(self, query: str, *, limit: int = 50) -> list[Device]:
        devices, _ = await self.list(page=1, page_size=limit, q=query)
        return devices


class SqlAlchemyInterfaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_device(self, device_id: UUID) -> list[Interface]:
        rows = (
            await self._session.execute(
                select(InterfaceModel).where(InterfaceModel.device_id == device_id).order_by(InterfaceModel.name)
            )
        ).scalars().all()
        return [
            Interface(
                id=r.id,
                device_id=r.device_id,
                name=r.name,
                if_index=r.if_index,
                description=r.description,
                mac=str(r.mac) if r.mac else None,
                mtu=r.mtu,
                duplex=r.duplex,
                speed_bps=r.speed_bps,
                poe_enabled=r.poe_enabled,
                admin_status=r.admin_status,
                oper_status=r.oper_status,
                is_trunk=r.is_trunk,
                native_vlan=r.native_vlan,
                lacp_group=r.lacp_group,
                attributes=dict(r.attributes or {}),
            )
            for r in rows
        ]

    async def replace_for_device(self, device_id: UUID, interfaces: list[Interface]) -> None:
        """Upsert interfaces by name — keep stable IDs so links/IPAM FKs survive rediscovery."""
        existing_rows = (
            await self._session.execute(
                select(InterfaceModel).where(InterfaceModel.device_id == device_id)
            )
        ).scalars().all()
        by_name = {r.name: r for r in existing_rows}
        keep: set[str] = set()
        for iface in interfaces:
            if not iface.name:
                continue
            keep.add(iface.name)
            row = by_name.get(iface.name)
            if row is None:
                row = InterfaceModel(id=iface.id or uuid4(), device_id=device_id, name=iface.name)
                self._session.add(row)
                by_name[iface.name] = row
            row.if_index = iface.if_index
            row.description = iface.description
            row.mac = iface.mac
            row.mtu = iface.mtu
            row.duplex = iface.duplex
            row.speed_bps = iface.speed_bps
            row.poe_enabled = iface.poe_enabled
            row.admin_status = iface.admin_status
            row.oper_status = iface.oper_status
            row.is_trunk = iface.is_trunk
            row.native_vlan = iface.native_vlan
            row.lacp_group = iface.lacp_group
            row.attributes = iface.attributes or {}
            # Expose stable id back to caller (link materialization)
            iface.id = row.id
        # Remove interfaces that disappeared — clear IPAM FKs first (no ON DELETE).
        stale_ids = [r.id for name, r in by_name.items() if name not in keep]
        if stale_ids:
            await self._session.execute(
                IpAddressModel.__table__.update()
                .where(IpAddressModel.interface_id.in_(stale_ids))
                .values(interface_id=None)
            )
            await self._session.execute(
                delete(InterfaceModel).where(InterfaceModel.id.in_(stale_ids))
            )
        await self._session.flush()


class SqlAlchemyLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Link]:
        rows = (await self._session.execute(select(LinkModel))).scalars().all()
        return [_link_from_model(r) for r in rows]

    async def upsert(self, link: Link) -> Link:
        a, b = sorted([link.interface_a_id, link.interface_b_id], key=str)
        existing = (
            await self._session.execute(
                select(LinkModel).where(LinkModel.interface_a_id == a, LinkModel.interface_b_id == b)
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = LinkModel(id=link.id, interface_a_id=a, interface_b_id=b)
            self._session.add(existing)
        existing.discovery_method = link.discovery_method.value
        existing.speed_bps = link.speed_bps
        existing.is_lacp = link.is_lacp
        existing.lacp_key = link.lacp_key
        existing.is_trunk = link.is_trunk
        existing.vlans = link.vlans
        existing.confidence = link.confidence
        existing.last_confirmed_at = link.last_confirmed_at or datetime.now(UTC)
        existing.media = link.media
        existing.link_status = link.link_status
        existing.crc_errors = link.crc_errors
        existing.drops = link.drops
        existing.rx_utilization_pct = link.rx_utilization_pct
        existing.tx_utilization_pct = link.tx_utilization_pct
        existing.sfp_vendor = link.sfp_vendor
        existing.sfp_model = link.sfp_model
        existing.sfp_serial = link.sfp_serial
        existing.rx_optical_dbm = link.rx_optical_dbm
        existing.tx_optical_dbm = link.tx_optical_dbm
        existing.temperature_c = link.temperature_c
        existing.voltage = link.voltage
        existing.health = link.health
        existing.health_reasons = link.health_reasons
        await self._session.flush()
        link.interface_a_id = a
        link.interface_b_id = b
        return link


def _link_from_model(r: LinkModel) -> Link:
    return Link(
        id=r.id,
        interface_a_id=r.interface_a_id,
        interface_b_id=r.interface_b_id,
        discovery_method=DiscoveryMethod(r.discovery_method)
        if r.discovery_method in DiscoveryMethod._value2member_map_
        else DiscoveryMethod.ARP,
        speed_bps=r.speed_bps,
        is_lacp=r.is_lacp,
        lacp_key=r.lacp_key,
        is_trunk=r.is_trunk,
        vlans=list(r.vlans or []),
        confidence=r.confidence,
        last_confirmed_at=r.last_confirmed_at,
        media=getattr(r, "media", None) or "unknown",
        link_status=getattr(r, "link_status", None) or "unknown",
        crc_errors=getattr(r, "crc_errors", None),
        drops=getattr(r, "drops", None),
        rx_utilization_pct=getattr(r, "rx_utilization_pct", None),
        tx_utilization_pct=getattr(r, "tx_utilization_pct", None),
        sfp_vendor=getattr(r, "sfp_vendor", None),
        sfp_model=getattr(r, "sfp_model", None),
        sfp_serial=getattr(r, "sfp_serial", None),
        rx_optical_dbm=getattr(r, "rx_optical_dbm", None),
        tx_optical_dbm=getattr(r, "tx_optical_dbm", None),
        temperature_c=getattr(r, "temperature_c", None),
        voltage=getattr(r, "voltage", None),
        health=getattr(r, "health", None) or "unknown",
        health_reasons=list(getattr(r, "health_reasons", None) or []),
    )


class SqlAlchemyNeighborRepository:
    """Persists LLDP/CDP adjacency facts (Smart Discovery enrichment)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_device(self, device_id: UUID, neighbors: list[NeighborFact]) -> None:
        await self._session.execute(delete(LldpNeighborModel).where(LldpNeighborModel.device_id == device_id))
        for n in neighbors:
            self._session.add(
                LldpNeighborModel(
                    id=uuid4(),
                    device_id=device_id,
                    local_interface=n.local_interface,
                    remote_hostname=n.remote_hostname,
                    remote_interface=n.remote_interface,
                    remote_chassis_id=n.remote_chassis_id,
                    remote_mgmt_ip=n.remote_mgmt_ip,
                    protocol=n.protocol,
                    raw=n.attributes or {},
                )
            )
        await self._session.flush()


class SqlAlchemyFdbRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_device(self, device_id: UUID, entries: list[FdbEntry]) -> None:
        await self._session.execute(delete(FdbEntryModel).where(FdbEntryModel.device_id == device_id))
        for e in entries:
            if not e.mac:
                continue
            self._session.add(
                FdbEntryModel(
                    id=uuid4(),
                    device_id=device_id,
                    mac=e.mac,
                    vlan_id=e.vlan_id,
                    interface=e.interface or "unknown",
                )
            )
        await self._session.flush()


class SqlAlchemyArpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_device(self, device_id: UUID, entries: list[ArpEntry]) -> None:
        await self._session.execute(delete(ArpEntryModel).where(ArpEntryModel.device_id == device_id))
        for e in entries:
            if not e.mac or not e.ip:
                continue
            self._session.add(
                ArpEntryModel(
                    id=uuid4(),
                    device_id=device_id,
                    ip=e.ip,
                    mac=e.mac,
                    interface=e.interface,
                )
            )
        await self._session.flush()


class SqlAlchemyVlanRepository:
    """Per-device VLAN table used by the VLAN Explorer aggregation query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_device(self, device_id: UUID, vlans: list[dict[str, Any]]) -> None:
        await self._session.execute(delete(VlanModel).where(VlanModel.device_id == device_id))
        seen: set[int] = set()
        for v in vlans:
            try:
                vid = int(v.get("vlan_id"))
            except (TypeError, ValueError):
                continue
            if vid in seen:
                continue
            seen.add(vid)
            self._session.add(
                VlanModel(id=uuid4(), device_id=device_id, vlan_id=vid, name=v.get("name"))
            )
        await self._session.flush()


class SqlAlchemyRouteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_device(self, device_id: UUID, routes: list[RouteFact]) -> None:
        await self._session.execute(delete(RouteModel).where(RouteModel.device_id == device_id))
        for r in routes:
            if not r.destination:
                continue
            try:
                self._session.add(
                    RouteModel(
                        id=uuid4(),
                        device_id=device_id,
                        destination=r.destination,
                        next_hop=r.next_hop,
                        interface=r.interface,
                        protocol=r.protocol,
                        metric=r.metric,
                    )
                )
            except Exception:  # noqa: BLE001 — skip malformed CIDR from vendor parsing
                continue
        await self._session.flush()


class SqlAlchemySnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: Snapshot) -> Snapshot:
        m = SnapshotModel(
            id=snapshot.id,
            discovery_job_id=snapshot.discovery_job_id,
            label=snapshot.label,
            checksum=snapshot.checksum,
            summary=snapshot.summary,
            payload=snapshot.payload,
            created_at=snapshot.created_at,
        )
        self._session.add(m)
        await self._session.flush()
        return snapshot

    async def get(self, snapshot_id: UUID) -> Snapshot | None:
        m = await self._session.get(SnapshotModel, snapshot_id)
        if not m:
            return None
        return Snapshot(
            id=m.id,
            discovery_job_id=m.discovery_job_id,
            label=m.label,
            created_at=m.created_at,
            checksum=m.checksum,
            summary=dict(m.summary or {}),
            payload=dict(m.payload or {}),
        )

    async def list(self) -> list[Snapshot]:
        rows = (
            await self._session.execute(select(SnapshotModel).order_by(SnapshotModel.created_at.desc()))
        ).scalars().all()
        return [
            Snapshot(
                id=m.id,
                discovery_job_id=m.discovery_job_id,
                label=m.label,
                created_at=m.created_at,
                checksum=m.checksum,
                summary=dict(m.summary or {}),
                payload={},
            )
            for m in rows
        ]


class SqlAlchemyDiscoverySeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[DiscoverySeed]:
        rows = (await self._session.execute(select(DiscoverySeedModel))).scalars().all()
        result: list[DiscoverySeed] = []
        for r in rows:
            raw_ids = r.credential_profile_ids or []
            ids: list[UUID] = []
            for x in raw_ids:
                try:
                    ids.append(x if isinstance(x, UUID) else UUID(str(x)))
                except (ValueError, TypeError):
                    continue
            result.append(
                DiscoverySeed(
                    id=r.id,
                    target=r.target,
                    label=r.label,
                    enabled=bool(r.enabled),
                    credential_profile_ids=ids,
                )
            )
        return result

    async def add(self, seed: DiscoverySeed) -> DiscoverySeed:
        m = DiscoverySeedModel(
            id=seed.id,
            target=seed.target,
            label=seed.label,
            enabled=seed.enabled,
            credential_profile_ids=[str(x) for x in seed.credential_profile_ids],
            options={},
        )
        self._session.add(m)
        await self._session.flush()
        return seed

    async def delete(self, seed_id: UUID) -> None:
        await self._session.execute(delete(DiscoverySeedModel).where(DiscoverySeedModel.id == seed_id))
        await self._session.flush()

    async def get_many(self, seed_ids: list[UUID]) -> list[DiscoverySeed]:
        if not seed_ids:
            return await self.list()
        rows = (
            await self._session.execute(select(DiscoverySeedModel).where(DiscoverySeedModel.id.in_(seed_ids)))
        ).scalars().all()
        return [
            DiscoverySeed(
                id=r.id,
                target=r.target,
                label=r.label,
                enabled=bool(r.enabled),
                credential_profile_ids=[
                    x if isinstance(x, UUID) else UUID(str(x))
                    for x in (r.credential_profile_ids or [])
                    if x
                ],
            )
            for r in rows
        ]


class SqlAlchemyDiscoveryJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: DiscoveryJob) -> DiscoveryJob:
        m = DiscoveryJobModel(
            id=job.id,
            status=job.status.value,
            started_at=job.started_at,
            finished_at=job.finished_at,
            config=job.config,
            stats=job.stats,
            error=job.error,
        )
        self._session.add(m)
        await self._session.flush()
        return job

    async def get(self, job_id: UUID) -> DiscoveryJob | None:
        # populate_existing so cancel flags from other sessions are visible mid-run
        m = await self._session.get(DiscoveryJobModel, job_id, populate_existing=True)
        if not m:
            return None
        return DiscoveryJob(
            id=m.id,
            status=JobStatus(m.status),
            started_at=m.started_at,
            finished_at=m.finished_at,
            config=dict(m.config or {}),
            stats=dict(m.stats or {}),
            error=m.error,
        )

    async def list(self) -> list[DiscoveryJob]:
        rows = (
            await self._session.execute(select(DiscoveryJobModel).order_by(DiscoveryJobModel.created_at.desc()))
        ).scalars().all()
        result: list[DiscoveryJob] = []
        for m in rows:
            try:
                status = JobStatus(m.status)
            except ValueError:
                status = JobStatus.FAILED
            result.append(
                DiscoveryJob(
                    id=m.id,
                    status=status,
                    started_at=m.started_at,
                    finished_at=m.finished_at,
                    config=dict(m.config or {}),
                    stats=dict(m.stats or {}),
                    error=m.error,
                )
            )
        return result

    async def update(self, job: DiscoveryJob) -> DiscoveryJob:
        m = await self._session.get(DiscoveryJobModel, job.id)
        if m is None:
            return await self.add(job)
        m.status = job.status.value
        m.started_at = job.started_at
        m.finished_at = job.finished_at
        m.config = job.config
        m.stats = job.stats
        m.error = job.error
        await self._session.flush()
        return job


class SqlAlchemyAuditLogger:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        source_ip: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        from netatlas.infrastructure.persistence.models import AuditEventModel

        self._session.add(
            AuditEventModel(
                actor_user_id=actor_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                source_ip=source_ip,
                details=details or {},
            )
        )
        await self._session.flush()

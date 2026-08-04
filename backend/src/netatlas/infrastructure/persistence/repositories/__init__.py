"""Repository adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.domain.entities import Device, DiscoveryJob, DiscoverySeed, Interface, Link, Snapshot
from netatlas.domain.value_objects import DevicePlatform, DeviceStatus, DiscoveryMethod, JobStatus
from netatlas.infrastructure.persistence.models import (
    DeviceModel,
    DiscoveryJobModel,
    DiscoverySeedModel,
    InterfaceModel,
    LinkModel,
    SnapshotModel,
)


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
    )


class SqlAlchemyDeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, device_id: UUID) -> Device | None:
        m = await self._session.get(DeviceModel, device_id)
        return _device_from_model(m) if m else None

    async def list(
        self, *, page: int, page_size: int, q: str | None = None, vendor: str | None = None
    ) -> tuple[list[Device], int]:
        stmt = select(DeviceModel)
        count_stmt = select(func.count()).select_from(DeviceModel)
        if q:
            like = f"%{q}%"
            filt = or_(
                DeviceModel.hostname.ilike(like),
                DeviceModel.serial.ilike(like),
                DeviceModel.model.ilike(like),
                DeviceModel.vendor.ilike(like),
                func.host(DeviceModel.management_ip).ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        if vendor:
            stmt = stmt.where(DeviceModel.vendor.ilike(vendor))
            count_stmt = count_stmt.where(DeviceModel.vendor.ilike(vendor))
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
        existing.last_seen_at = now
        existing.attributes = device.attributes
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
        await self._session.execute(delete(InterfaceModel).where(InterfaceModel.device_id == device_id))
        for iface in interfaces:
            self._session.add(
                InterfaceModel(
                    id=iface.id,
                    device_id=device_id,
                    name=iface.name,
                    if_index=iface.if_index,
                    description=iface.description,
                    mac=iface.mac,
                    mtu=iface.mtu,
                    duplex=iface.duplex,
                    speed_bps=iface.speed_bps,
                    poe_enabled=iface.poe_enabled,
                    admin_status=iface.admin_status,
                    oper_status=iface.oper_status,
                    is_trunk=iface.is_trunk,
                    native_vlan=iface.native_vlan,
                    lacp_group=iface.lacp_group,
                    attributes=iface.attributes,
                )
            )
        await self._session.flush()


class SqlAlchemyLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Link]:
        rows = (await self._session.execute(select(LinkModel))).scalars().all()
        return [
            Link(
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
            )
            for r in rows
        ]

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
        await self._session.flush()
        link.interface_a_id = a
        link.interface_b_id = b
        return link


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
        m = await self._session.get(DiscoveryJobModel, job_id)
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

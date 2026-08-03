"""Device and search routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import device_to_dict, get_db, require_permission
from netatlas.infrastructure.persistence.models import (
    DeviceMetricModel,
    DeviceModel,
    InterfaceModel,
    IpAddressModel,
)
from netatlas.infrastructure.persistence.repositories import (
    SqlAlchemyDeviceRepository,
    SqlAlchemyInterfaceRepository,
)

router = APIRouter(tags=["devices"])


@router.get("/devices")
async def list_devices(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str | None = None,
    vendor: str | None = None,
) -> dict[str, Any]:
    repo = SqlAlchemyDeviceRepository(session)
    items, total = await repo.list(page=page, page_size=page_size, q=q, vendor=vendor)
    return {
        "items": [device_to_dict(d) for d in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/devices/{device_id}")
async def get_device(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    repo = SqlAlchemyDeviceRepository(session)
    device = await repo.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ifaces = await SqlAlchemyInterfaceRepository(session).list_for_device(device_id)
    data = device_to_dict(device)
    data["attributes"] = device.attributes
    data["interfaces"] = [
        {
            "id": str(i.id),
            "name": i.name,
            "description": i.description,
            "mac": i.mac,
            "mtu": i.mtu,
            "duplex": i.duplex,
            "speed_bps": i.speed_bps,
            "poe_enabled": i.poe_enabled,
            "admin_status": i.admin_status,
            "oper_status": i.oper_status,
            "is_trunk": i.is_trunk,
            "native_vlan": i.native_vlan,
            "lacp_group": i.lacp_group,
        }
        for i in ifaces
    ]
    return data


@router.get("/devices/{device_id}/interfaces")
async def list_interfaces(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    detail = await get_device(device_id, session, _user)
    return detail["interfaces"]


@router.get("/devices/{device_id}/metrics")
async def device_metrics(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("monitoring:read"))],
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(DeviceMetricModel)
            .where(DeviceMetricModel.device_id == device_id)
            .order_by(DeviceMetricModel.collected_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "cpu_percent": r.cpu_percent,
                "memory_percent": r.memory_percent,
                "temperature_c": r.temperature_c,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            }
            for r in rows
        ]
    }


@router.get("/devices/{device_id}/neighbors")
async def device_neighbors(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    from netatlas.infrastructure.persistence.models import LldpNeighborModel

    rows = (
        await session.execute(
            select(LldpNeighborModel).where(LldpNeighborModel.device_id == device_id)
        )
    ).scalars().all()
    return [
        {
            "local_interface": r.local_interface,
            "remote_hostname": r.remote_hostname,
            "remote_interface": r.remote_interface,
            "remote_chassis_id": r.remote_chassis_id,
            "remote_mgmt_ip": str(r.remote_mgmt_ip) if r.remote_mgmt_ip else None,
            "protocol": r.protocol,
        }
        for r in rows
    ]


@router.get("/devices/{device_id}/fdb")
async def device_fdb(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    from netatlas.infrastructure.persistence.models import FdbEntryModel

    rows = (
        await session.execute(select(FdbEntryModel).where(FdbEntryModel.device_id == device_id))
    ).scalars().all()
    return [
        {
            "mac": str(r.mac),
            "vlan_id": r.vlan_id,
            "interface": r.interface,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
        }
        for r in rows
    ]


@router.get("/devices/{device_id}/arp")
async def device_arp(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    from netatlas.infrastructure.persistence.models import ArpEntryModel

    rows = (
        await session.execute(select(ArpEntryModel).where(ArpEntryModel.device_id == device_id))
    ).scalars().all()
    return [
        {
            "ip": str(r.ip),
            "mac": str(r.mac),
            "interface": r.interface,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
        }
        for r in rows
    ]


@router.get("/devices/{device_id}/routes")
async def device_routes(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> list[dict[str, Any]]:
    from netatlas.infrastructure.persistence.models import RouteModel

    rows = (
        await session.execute(select(RouteModel).where(RouteModel.device_id == device_id))
    ).scalars().all()
    return [
        {
            "destination": str(r.destination),
            "next_hop": str(r.next_hop) if r.next_hop else None,
            "interface": r.interface,
            "protocol": r.protocol,
            "metric": r.metric,
        }
        for r in rows
    ]


@router.get("/search")
async def search(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
    q: str = Query(min_length=1),
) -> dict[str, Any]:
    like = f"%{q}%"
    devices = (
        await session.execute(
            select(DeviceModel)
            .where(
                or_(
                    DeviceModel.hostname.ilike(like),
                    DeviceModel.serial.ilike(like),
                    DeviceModel.vendor.ilike(like),
                    DeviceModel.model.ilike(like),
                )
            )
            .limit(50)
        )
    ).scalars().all()
    interfaces = (
        await session.execute(
            select(InterfaceModel)
            .where(or_(InterfaceModel.name.ilike(like), InterfaceModel.description.ilike(like)))
            .limit(50)
        )
    ).scalars().all()
    addresses = (
        await session.execute(select(IpAddressModel).where(IpAddressModel.hostname.ilike(like)).limit(50))
    ).scalars().all()
    return {
        "devices": [
            {
                "id": str(d.id),
                "hostname": d.hostname,
                "vendor": d.vendor,
                "model": d.model,
                "serial": d.serial,
                "management_ip": str(d.management_ip) if d.management_ip else None,
                "platform": d.platform,
                "status": d.status,
            }
            for d in devices
        ],
        "interfaces": [
            {
                "id": str(i.id),
                "name": i.name,
                "description": i.description,
                "device_id": str(i.device_id),
                "oper_status": i.oper_status,
            }
            for i in interfaces
        ],
        "addresses": [
            {
                "id": str(a.id),
                "address": str(a.address),
                "hostname": a.hostname,
                "status": a.status,
                "is_conflict": a.is_conflict,
            }
            for a in addresses
        ],
    }

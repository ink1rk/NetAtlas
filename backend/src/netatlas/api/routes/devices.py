"""Device and search routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import device_to_dict, get_db, require_permission
from netatlas.infrastructure.collectors.base.metric_catalog import METRIC_CATALOG
from netatlas.infrastructure.persistence.models import (
    CredentialProfileModel,
    DeviceCredentialModel,
    DeviceMetricModel,
    DeviceModel,
    InterfaceModel,
    IpAddressModel,
    VlanModel,
)
from netatlas.infrastructure.persistence.repositories import (
    SqlAlchemyDeviceRepository,
    SqlAlchemyInterfaceRepository,
)
from netatlas.infrastructure.security.credential_resolver import bind_device_credentials

router = APIRouter(tags=["devices"])


class DeviceCredentialsBody(BaseModel):
    credential_profile_ids: list[UUID] = Field(default_factory=list)


@router.get("/devices")
async def list_devices(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str | None = None,
    vendor: str | None = None,
    status: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    repo = SqlAlchemyDeviceRepository(session)
    items, total = await repo.list(
        page=page, page_size=page_size, q=q, vendor=vendor, status=status, platform=platform
    )
    return {
        "items": [device_to_dict(d) for d in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/devices/facets")
async def device_facets(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    """Distinct vendors/platforms/statuses for filter suggestions."""
    vendors = (
        await session.execute(
            select(DeviceModel.vendor)
            .where(DeviceModel.vendor.is_not(None), DeviceModel.vendor != "")
            .distinct()
            .order_by(DeviceModel.vendor)
            .limit(100)
        )
    ).scalars().all()
    platforms = (
        await session.execute(
            select(DeviceModel.platform)
            .where(DeviceModel.platform.is_not(None), DeviceModel.platform != "")
            .distinct()
            .order_by(DeviceModel.platform)
            .limit(50)
        )
    ).scalars().all()
    statuses = (
        await session.execute(
            select(DeviceModel.status)
            .where(DeviceModel.status.is_not(None), DeviceModel.status != "")
            .distinct()
            .order_by(DeviceModel.status)
        )
    ).scalars().all()
    return {
        "vendors": list(vendors),
        "platforms": list(platforms),
        "statuses": list(statuses),
        "suggested_vendors": ["Eltex", "MikroTik", "UniFi", "Proxmox", "VMware", "Ideco", "Kyocera"],
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
    items = [
        {
            "cpu_percent": r.cpu_percent,
            "memory_percent": r.memory_percent,
            "temperature_c": r.temperature_c,
            "extras": r.extras or {},
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            "timestamp": r.collected_at.isoformat() if r.collected_at else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "history": list(reversed(items)),
        "latest": items[0] if items else None,
    }


@router.get("/devices/{device_id}/credentials")
async def list_device_credentials(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("credentials:read"))],
) -> dict[str, Any]:
    if not await session.get(DeviceModel, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    links = (
        await session.execute(
            select(DeviceCredentialModel, CredentialProfileModel)
            .join(CredentialProfileModel, CredentialProfileModel.id == DeviceCredentialModel.credential_profile_id)
            .where(DeviceCredentialModel.device_id == device_id)
        )
    ).all()
    return {
        "device_id": str(device_id),
        "items": [
            {
                "id": str(link.id),
                "credential_profile_id": str(profile.id),
                "name": profile.name,
                "protocol": profile.protocol,
            }
            for link, profile in links
        ],
    }


@router.put("/devices/{device_id}/credentials")
async def set_device_credentials(
    device_id: UUID,
    body: DeviceCredentialsBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("credentials:write"))],
) -> dict[str, Any]:
    if not await session.get(DeviceModel, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    existing = (
        await session.execute(
            select(DeviceCredentialModel).where(DeviceCredentialModel.device_id == device_id)
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    created = await bind_device_credentials(session, device_id, body.credential_profile_ids)
    await session.commit()
    return {"device_id": str(device_id), "linked": created, "credential_profile_ids": [str(x) for x in body.credential_profile_ids]}


@router.delete("/devices/{device_id}/credentials/{profile_id}", status_code=204)
async def detach_device_credential(
    device_id: UUID,
    profile_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("credentials:write"))],
) -> None:
    row = (
        await session.execute(
            select(DeviceCredentialModel).where(
                DeviceCredentialModel.device_id == device_id,
                DeviceCredentialModel.credential_profile_id == profile_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Credential link not found")
    await session.delete(row)
    await session.commit()


@router.get("/monitoring/metrics-catalog")
async def metrics_catalog(
    _user: Annotated[Any, Depends(require_permission("monitoring:read"))],
) -> dict[str, Any]:
    return {"items": METRIC_CATALOG}


@router.post("/monitoring/collect-now", status_code=202)
async def collect_metrics_now(
    _user: Annotated[Any, Depends(require_permission("monitoring:read"))],
) -> dict[str, Any]:
    """Immediate metrics sweep + identity enrichment for Unknown Device stubs.

    Runs inline so SNMPv2 profiles assigned after discovery can fill hostname /
    vendor / model / interfaces without waiting for Celery beat.
    """
    from netatlas.workers.celery_app import _collect_metrics

    stats = await _collect_metrics()
    return {"status": "completed", "dispatch": "inline", **stats}


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


@router.get("/devices/{device_id}/bridge")
async def device_bridge(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    """Mikrotik Bridge View: bridges, ports (PVID/tagged/untagged/horizon), RSTP, VLAN table."""
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    bridge = (device.attributes or {}).get("bridge") or {}
    return {
        "device_id": str(device_id),
        "supported": bool(bridge),
        "bridges": bridge.get("bridges", []),
        "ports": bridge.get("ports", []),
        "vlan_table": bridge.get("vlan_table", []),
    }


@router.get("/devices/{device_id}/printer")
async def device_printer(
    device_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
) -> dict[str, Any]:
    """Printer Discovery: consumables, page count, tray/error state for map badges."""
    device = await session.get(DeviceModel, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    attrs = device.attributes or {}
    printer = dict(attrs.get("printer") or {})
    if attrs.get("device_class") == "printer" or attrs.get("toner_percent") is not None:
        latest = (
            await session.execute(
                select(DeviceMetricModel)
                .where(DeviceMetricModel.device_id == device_id)
                .order_by(DeviceMetricModel.collected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest and latest.extras:
            for key in (
                "black_toner_percent",
                "cyan_toner_percent",
                "magenta_toner_percent",
                "yellow_toner_percent",
                "waste_toner_percent",
                "total_pages",
                "paper_empty",
                "status",
                "printer_errors",
            ):
                if key in latest.extras and latest.extras[key] is not None:
                    printer[key.replace("printer_errors", "errors")] = latest.extras[key]
    return {
        "device_id": str(device_id),
        "supported": attrs.get("device_class") == "printer",
        "model": device.model,
        "serial": device.serial,
        "firmware": device.firmware,
        **printer,
    }


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
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    like = f"%{q.strip()}%"
    device_filters = [
        DeviceModel.hostname.ilike(like),
        DeviceModel.serial.ilike(like),
        DeviceModel.vendor.ilike(like),
        DeviceModel.model.ilike(like),
        DeviceModel.platform.ilike(like),
        DeviceModel.firmware.ilike(like),
        DeviceModel.os_version.ilike(like),
    ]
    # Management IP / MAC text search
    try:
        from sqlalchemy import String, cast

        device_filters.append(cast(DeviceModel.management_ip, String).ilike(like))
        device_filters.append(cast(DeviceModel.management_mac, String).ilike(like))
    except Exception:
        pass

    devices = (
        await session.execute(
            select(DeviceModel).where(or_(*device_filters)).order_by(DeviceModel.hostname).limit(limit)
        )
    ).scalars().all()
    interfaces = (
        await session.execute(
            select(InterfaceModel)
            .where(
                or_(
                    InterfaceModel.name.ilike(like),
                    InterfaceModel.description.ilike(like),
                    cast(InterfaceModel.mac, String).ilike(like) if True else InterfaceModel.name.ilike(like),
                )
            )
            .limit(limit)
        )
    ).scalars().all()
    addresses = (
        await session.execute(
            select(IpAddressModel)
            .where(
                or_(
                    IpAddressModel.hostname.ilike(like),
                    cast(IpAddressModel.address, String).ilike(like),
                )
            )
            .limit(limit)
        )
    ).scalars().all()
    vlan_filters = [VlanModel.name.ilike(like), VlanModel.description.ilike(like)]
    q_stripped = q.strip()
    if q_stripped.isdigit():
        vlan_filters.append(VlanModel.vlan_id == int(q_stripped))
    vlans = (
        await session.execute(select(VlanModel).where(or_(*vlan_filters)).limit(limit))
    ).scalars().all()
    return {
        "query": q.strip(),
        "devices": [
            {
                "id": str(d.id),
                "hostname": d.hostname,
                "vendor": d.vendor,
                "model": d.model,
                "serial": d.serial,
                "management_ip": str(d.management_ip) if d.management_ip else None,
                "management_mac": str(d.management_mac) if d.management_mac else None,
                "platform": d.platform,
                "status": d.status,
                "network_role": getattr(d, "network_role", None),
            }
            for d in devices
        ],
        "interfaces": [
            {
                "id": str(i.id),
                "name": i.name,
                "description": i.description,
                "device_id": str(i.device_id),
                "mac": str(i.mac) if i.mac else None,
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
        "vlans": [
            {
                "id": str(v.id),
                "vlan_id": v.vlan_id,
                "name": v.name,
                "description": v.description,
            }
            for v in vlans
        ],
    }


@router.get("/search/suggest")
async def search_suggest(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[Any, Depends(require_permission("inventory:read"))],
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(8, ge=1, le=20),
) -> dict[str, Any]:
    """Lightweight autocomplete suggestions for the global/device search."""

    like = f"%{q.strip()}%"
    rows = (
        await session.execute(
            select(DeviceModel)
            .where(
                or_(
                    DeviceModel.hostname.ilike(like),
                    DeviceModel.vendor.ilike(like),
                    DeviceModel.model.ilike(like),
                    cast(DeviceModel.management_ip, String).ilike(like),
                )
            )
            .order_by(DeviceModel.hostname)
            .limit(limit)
        )
    ).scalars().all()
    suggestions = [
        {
            "type": "device",
            "id": str(d.id),
            "label": d.hostname,
            "subtitle": " · ".join(
                p for p in [str(d.management_ip) if d.management_ip else None, d.vendor, d.platform] if p
            ),
            "href": f"/pages/device-detail.html?id={d.id}",
        }
        for d in rows
    ]
    q_stripped = q.strip()
    vlan_filters = [VlanModel.name.ilike(like)]
    if q_stripped.isdigit():
        vlan_filters.append(VlanModel.vlan_id == int(q_stripped))
    vlan_rows = (
        await session.execute(select(VlanModel).where(or_(*vlan_filters)).limit(max(1, limit // 2)))
    ).scalars().all()
    seen_vlans: set[int] = set()
    for v in vlan_rows:
        if v.vlan_id in seen_vlans:
            continue
        seen_vlans.add(v.vlan_id)
        suggestions.append(
            {
                "type": "vlan",
                "id": str(v.vlan_id),
                "label": f"VLAN {v.vlan_id}" + (f" · {v.name}" if v.name else ""),
                "subtitle": "VLAN",
                "href": f"/pages/dashboard.html?ws=vlans&vlan={v.vlan_id}",
            }
        )
    return {"query": q.strip(), "suggestions": suggestions[:limit]}
